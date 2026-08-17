"""Step definitions for reading_generation.feature."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from backend.app.config import settings
from backend.app.services.reading import LinkCheck
from backend.tests.bdd.conftest import (
    create_allowlist_entries,
    create_feedback,
    create_onboarding,
    create_reading_recommendation,
    create_topics,
    make_reading_generation_response,
    run_async,
)

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

scenarios("reading_generation.feature")


@pytest.fixture(autouse=True)
def _no_feed_candidates(monkeypatch):
    """Pin these scenarios to the recall path (LLM supplies its own URLs).

    Every scenario here exercises a *filter* — disliked, duplicate, off-allowlist,
    bad link, duplicate topic — using a stubbed LLM response that carries a URL.
    Left on, feed sourcing would reach the real network during the test run and,
    worse, put the pipeline in selection mode where a response with no
    ``candidate_id`` is correctly discarded and every scenario stores nothing.

    Selection mode is covered separately in ``test_reading_candidates.py``.
    """
    monkeypatch.setattr(settings, "reading_use_feed_candidates", False)


# ---------------------------------------------------------------------------
# Background steps
# ---------------------------------------------------------------------------


@given("onboarding has been completed")
def given_onboarding(bdd_db, ctx):
    state = create_onboarding(bdd_db)
    run_async(bdd_db.commit())
    ctx["onboarding"] = state


@given("the Knowledge Profile has topics")
def given_topics(bdd_db, ctx):
    topics = create_topics(bdd_db)
    run_async(bdd_db.commit())
    ctx["topics"] = topics


# ---------------------------------------------------------------------------
# Generate readings
# ---------------------------------------------------------------------------


@given(parsers.parse('the reading allowlist contains "{domain1}" and "{domain2}"'))
def given_allowlist_two(bdd_db, ctx, domain1, domain2):
    entries = create_allowlist_entries(bdd_db, [(domain1, domain1), (domain2, domain2)])
    run_async(bdd_db.commit())
    ctx["allowlist"] = entries


@when("the reading generation pipeline runs")
def when_generate_readings(bdd_db, ctx):
    from backend.app.pipelines.reading_pipeline import generate_readings

    mock_response = make_reading_generation_response()

    with (
        patch(
            "backend.app.pipelines.reading_pipeline.llm_client.chat_completion_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_llm,
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.check_links",
            new_callable=AsyncMock,
            return_value={},  # empty → pipeline skips link verification
        ),
    ):
        readings = run_async(generate_readings(bdd_db))
        run_async(bdd_db.commit())

    ctx["readings"] = readings
    # Keep the user-role prompt so scenarios can assert on what the signals
    # actually put in front of the model, not merely on what was stored.
    ctx["prompt"] = mock_llm.call_args.kwargs["messages"][1]["content"]


@then("reading recommendations should be created")
def then_readings_created(ctx):
    assert len(ctx["readings"]) > 0


@then("all recommendations should be from allowlisted domains")
def then_all_allowlisted(ctx):
    for r in ctx["readings"]:
        assert r.source_domain in ("go.dev", "blog.golang.org")


# ---------------------------------------------------------------------------
# Filtered domain scenario
# ---------------------------------------------------------------------------


@given(parsers.parse('the reading allowlist contains only "{domain}"'))
def given_allowlist_one(bdd_db, ctx, domain):
    entries = create_allowlist_entries(bdd_db, [(domain, domain)])
    run_async(bdd_db.commit())
    ctx["allowlist"] = entries


@when("the reading generation pipeline runs with a response containing a non-allowlisted domain")
def when_generate_with_bad_domain(bdd_db, ctx):
    from backend.app.pipelines.reading_pipeline import generate_readings

    # LLM returns recommendations from both go.dev and blog.golang.org,
    # but only go.dev is on the allowlist.
    mock_response = make_reading_generation_response()

    with (
        patch(
            "backend.app.pipelines.reading_pipeline.llm_client.chat_completion_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ),
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.check_links",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        readings = run_async(generate_readings(bdd_db))
        run_async(bdd_db.commit())

    ctx["readings"] = readings


@then(parsers.parse('only recommendations from "{domain}" should be stored'))
def then_only_domain(ctx, domain):
    assert len(ctx["readings"]) > 0
    for r in ctx["readings"]:
        assert r.source_domain == domain


# ---------------------------------------------------------------------------
# Unreachable URL scenario
# ---------------------------------------------------------------------------


@when("the reading generation pipeline runs and one URL returns 404")
def when_generate_with_broken_url(bdd_db, ctx):
    from backend.app.pipelines.reading_pipeline import generate_readings

    mock_response = make_reading_generation_response()
    # Default recs: effective_go (reachable) and blog.golang.org/pipelines (broken)
    url_status = {
        "https://go.dev/doc/effective_go#concurrency": LinkCheck(
            "https://go.dev/doc/effective_go#concurrency",
            reachable=True,
            final_url="https://go.dev/doc/effective_go",
        ),
        "https://blog.golang.org/pipelines": LinkCheck(
            "https://blog.golang.org/pipelines",
            reachable=False,
            reason="HTTP 404",
        ),
    }

    with (
        patch(
            "backend.app.pipelines.reading_pipeline.llm_client.chat_completion_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ),
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.check_links",
            new_callable=AsyncMock,
            return_value=url_status,
        ),
    ):
        readings = run_async(generate_readings(bdd_db))
        run_async(bdd_db.commit())

    ctx["readings"] = readings


@then("only recommendations with reachable URLs should be stored")
def then_only_reachable(ctx):
    assert len(ctx["readings"]) == 1
    assert ctx["readings"][0].url == "https://go.dev/doc/effective_go#concurrency"


# ---------------------------------------------------------------------------
# Link verification scenarios
# ---------------------------------------------------------------------------
# A reachable 200 is not evidence that a link is the article it claims to be.
# These cover the two ways a real page can still be the wrong page.
def _run_pipeline(bdd_db, ctx, recommendations, link_checks):
    from backend.app.pipelines.reading_pipeline import generate_readings

    with (
        patch(
            "backend.app.pipelines.reading_pipeline.llm_client.chat_completion_json",
            new_callable=AsyncMock,
            return_value=make_reading_generation_response(recommendations),
        ),
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.check_links",
            new_callable=AsyncMock,
            return_value=link_checks,
        ),
    ):
        ctx["readings"] = run_async(generate_readings(bdd_db))
        run_async(bdd_db.commit())


def _rec(title, url, topic):
    return {
        "title": title,
        "url": url,
        "source_domain": "go.dev",
        "description": "d",
        "recommendation_type": "deep_dive",
        "target_topic": topic,
        "rationale": "r",
    }


@when("the reading generation pipeline runs and one URL is a site landing page")
def when_generate_with_landing_page(bdd_db, ctx):
    good = "https://go.dev/doc/effective_go"
    landing = "https://go.dev/blog"
    _run_pipeline(
        bdd_db,
        ctx,
        [
            _rec("Effective Go", good, "Go basics"),
            _rec("Go Generics In Depth", landing, "Go generics"),
        ],
        {
            good: LinkCheck(good, reachable=True, final_url=good, page_titles=("Effective Go",)),
            landing: LinkCheck(
                landing, reachable=True, final_url=landing, page_titles=("The Go Blog",)
            ),
        },
    )


@then("the landing page should not appear in the batch")
def then_no_landing_page(ctx):
    urls = [r.url for r in ctx["readings"]]
    assert urls == ["https://go.dev/doc/effective_go"]


@then("the processing log should record it as a landing page")
def then_log_records_landing_page(bdd_db, ctx):
    log = _latest_reading_log(bdd_db)
    skipped = (log.metadata_ or {}).get("skipped_bad_link", [])
    assert any("landing page" in s.get("reason", "") for s in skipped), skipped


@when("the reading generation pipeline runs and one URL resolves to an unrelated page")
def when_generate_with_mismatched_page(bdd_db, ctx):
    good = "https://go.dev/doc/effective_go"
    wrong = "https://go.dev/doc/faq"
    _run_pipeline(
        bdd_db,
        ctx,
        [
            _rec("Effective Go", good, "Go basics"),
            _rec("Understanding Go Scheduler Internals", wrong, "Go runtime"),
        ],
        {
            good: LinkCheck(good, reachable=True, final_url=good, page_titles=("Effective Go",)),
            wrong: LinkCheck(
                wrong,
                reachable=True,
                final_url=wrong,
                page_titles=("Frequently Asked Questions About Modules",),
            ),
        },
    )


@then("the mismatched link should not appear in the batch")
def then_no_mismatch(ctx):
    urls = [r.url for r in ctx["readings"]]
    assert urls == ["https://go.dev/doc/effective_go"]


@when("the reading generation pipeline runs with a URL labelled with an allowlisted domain")
def when_generate_with_mislabelled_domain(bdd_db, ctx):
    # The exact production failure: blog.langchain.dev stored under a
    # thenewstack.io label because a matching source_domain satisfied the check
    # on its own.
    url = "https://blog.langchain.dev"
    _run_pipeline(
        bdd_db,
        ctx,
        [_rec("Understanding LangChain and LangGraph", url, "LLM frameworks")],
        {url: LinkCheck(url, reachable=True, final_url=url, page_titles=("LangChain Blog",))},
    )


@then("no recommendations should be stored")
def then_nothing_stored(ctx):
    assert ctx["readings"] == []


# ---------------------------------------------------------------------------
# Engagement signals reaching the prompt
# ---------------------------------------------------------------------------
# read_at / saved_at / dismissed_at were recorded and read by nothing. These
# assert on the prompt rather than on what was stored, because that is where
# the signal either arrives or does not.
@given(parsers.parse('two readings from "{domain}" have been dismissed'))
def given_two_dismissed(bdd_db, ctx, domain):
    for i in range(2):
        create_reading_recommendation(
            bdd_db,
            url=f"https://{domain}/dismissed-{i}",
            source_domain=domain,
            title=f"Dismissed {i}",
            dismissed=True,
        )
    run_async(bdd_db.commit())


@then(parsers.parse('the prompt should downrank "{domain}"'))
def then_prompt_downranks(ctx, domain):
    section = ctx["prompt"].split("## Downranked domains")[1].split("##")[0]
    assert domain in section, section


@given(parsers.parse('a reading titled "{title}" has been saved'))
def given_saved_reading(bdd_db, ctx, title):
    create_reading_recommendation(
        bdd_db,
        url="https://go.dev/ref/mem",
        source_domain="go.dev",
        title=title,
        saved=True,
    )
    run_async(bdd_db.commit())


@then(parsers.parse('the prompt should offer "{title}" as a saved direction'))
def then_prompt_offers_saved(ctx, title):
    section = ctx["prompt"].split("## Liked directions")[1].split("##")[0]
    assert f'[saved] "{title}"' in section, section


# ---------------------------------------------------------------------------
# Helper: load the most recent reading-generation processing log
# ---------------------------------------------------------------------------


def _latest_reading_log(bdd_db):
    from sqlalchemy import select

    from backend.app.models.base import PipelineType
    from backend.app.models.settings import ProcessingLog

    stmt = (
        select(ProcessingLog)
        .where(ProcessingLog.pipeline == PipelineType.READING_GENERATION)
        .order_by(ProcessingLog.started_at.desc())
        .limit(1)
    )
    return run_async(bdd_db.execute(stmt)).scalar_one()


@then("the processing log should record the skipped URL")
def then_log_records_skipped(bdd_db, ctx):
    log = _latest_reading_log(bdd_db)
    skipped = (log.metadata_ or {}).get("skipped_bad_link", [])
    assert any("blog.golang.org/pipelines" in s.get("url", "") for s in skipped)


# ---------------------------------------------------------------------------
# Thumbs-up loop prevention scenario
# ---------------------------------------------------------------------------


@given(parsers.parse('I have thumbs-upped a previous reading at "{url}"'))
def given_thumbs_upped_reading(bdd_db, ctx, url):
    # Derive a plausible source_domain from the URL host segment.
    domain = url.split("://", 1)[-1].split("/", 1)[0]
    rec = create_reading_recommendation(
        bdd_db, url=url, source_domain=domain, title="Liked previous reading"
    )
    create_feedback(bdd_db, target_type="reading", target_id=rec.id, reaction="thumbs_up")
    run_async(bdd_db.commit())
    ctx["liked_url"] = url
    ctx["liked_reading"] = rec


@when("the reading generation pipeline runs and proposes that same URL again")
def when_generate_proposes_liked_url(bdd_db, ctx):
    from backend.app.pipelines.reading_pipeline import generate_readings

    liked_url = ctx["liked_url"]
    # LLM proposes the liked URL again, plus one fresh URL on a different topic
    # so the batch isn't entirely empty after the avoid-list filter fires.
    mock_response = make_reading_generation_response(
        recommendations=[
            {
                "title": "Re-proposing the liked one",
                "url": liked_url,
                "source_domain": liked_url.split("://", 1)[-1].split("/", 1)[0],
                "description": "Should be filtered as already-liked",
                "recommendation_type": "deep_dive",
                "target_topic": "Go concurrency patterns",
                "rationale": "LLM didn't realise the user already read this",
            },
            {
                "title": "A genuinely new piece",
                "url": "https://blog.golang.org/pipelines",
                "source_domain": "blog.golang.org",
                "description": "Different topic, should be stored",
                "recommendation_type": "next_frontier",
                "target_topic": "Go pipelines",
                "rationale": "Fresh material",
            },
        ]
    )

    with (
        patch(
            "backend.app.pipelines.reading_pipeline.llm_client.chat_completion_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ),
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.check_links",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        readings = run_async(generate_readings(bdd_db))
        run_async(bdd_db.commit())

    ctx["readings"] = readings


@then("the previously-liked URL should not appear in the new batch")
def then_liked_url_excluded(ctx):
    liked_url = ctx["liked_url"]
    new_urls = {r.url for r in ctx["readings"]}
    assert liked_url not in new_urls
    # Belt-and-braces: the *other* recommendation should still be there.
    assert len(ctx["readings"]) == 1


@then("the processing log should record one skipped already-liked recommendation")
def then_log_records_already_liked(bdd_db):
    log = _latest_reading_log(bdd_db)
    assert (log.metadata_ or {}).get("skipped_already_liked") == 1


# ---------------------------------------------------------------------------
# Diversity dedupe scenario
# ---------------------------------------------------------------------------


@when("the reading generation pipeline runs with two recommendations targeting the same topic")
def when_generate_two_same_topic(bdd_db, ctx):
    from backend.app.pipelines.reading_pipeline import generate_readings

    # Both recs share target_topic; both are domain-valid and reachable so the
    # *only* reason the second should be dropped is the diversity gate.
    mock_response = make_reading_generation_response(
        recommendations=[
            {
                "title": "Effective Go — Concurrency",
                "url": "https://go.dev/doc/effective_go#concurrency",
                "source_domain": "go.dev",
                "description": "Official guide",
                "recommendation_type": "deep_dive",
                "target_topic": "Go concurrency patterns",
                "rationale": "Strengthens current frontier",
            },
            {
                "title": "Go Blog — Pipelines",
                "url": "https://blog.golang.org/pipelines",
                "source_domain": "blog.golang.org",
                "description": "Pipelines patterns",
                "recommendation_type": "next_frontier",
                "target_topic": "Go concurrency patterns",
                "rationale": "Same topic — diversity gate should drop this",
            },
        ]
    )

    with (
        patch(
            "backend.app.pipelines.reading_pipeline.llm_client.chat_completion_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ),
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.check_links",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        readings = run_async(generate_readings(bdd_db))
        run_async(bdd_db.commit())

    ctx["readings"] = readings


@then("only one recommendation should be stored for that topic")
def then_one_per_topic(ctx):
    assert len(ctx["readings"]) == 1


@then("the processing log should record one skipped duplicate-topic recommendation")
def then_log_records_duplicate_topic(bdd_db):
    log = _latest_reading_log(bdd_db)
    md = log.metadata_ or {}
    assert md.get("skipped_duplicate_topic") == 1
    assert md.get("distinct_topics") == 1


# ---------------------------------------------------------------------------
# Duplicate URL (cross-batch) scenario
# ---------------------------------------------------------------------------


@given(parsers.parse('a reading at "{url}" already exists in the database'))
def given_existing_reading_url(bdd_db, ctx, url):
    reading = create_reading_recommendation(
        bdd_db,
        url=url,
        source_domain=url.split("://", 1)[-1].split("/", 1)[0],
        title="Original title",
    )
    run_async(bdd_db.commit())
    ctx["existing_url"] = url
    ctx["existing_reading"] = reading


@when("the reading generation pipeline runs and proposes that same URL with a different title")
def when_generate_proposes_existing_url(bdd_db, ctx):
    from backend.app.pipelines.reading_pipeline import generate_readings

    existing_url = ctx["existing_url"]
    domain = existing_url.split("://", 1)[-1].split("/", 1)[0]
    mock_response = make_reading_generation_response(
        recommendations=[
            {
                "title": "Completely Different Title for Same Page",
                "url": existing_url,
                "source_domain": domain,
                "description": "Different description, same URL",
                "recommendation_type": "deep_dive",
                "target_topic": "Kubernetes resource management",
                "rationale": "LLM suggested the same link it already stored",
            },
            {
                "title": "A genuinely new article",
                "url": "https://go.dev/doc/faq",
                "source_domain": "go.dev",
                "description": "Go FAQ — fresh content",
                "recommendation_type": "next_frontier",
                "target_topic": "Go language basics",
                "rationale": "New content",
            },
        ]
    )

    with (
        patch(
            "backend.app.pipelines.reading_pipeline.llm_client.chat_completion_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ),
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.check_links",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        readings = run_async(generate_readings(bdd_db))
        run_async(bdd_db.commit())

    ctx["readings"] = readings


@then("the duplicate URL should not appear in the new batch")
def then_duplicate_url_excluded(ctx):
    existing_url = ctx["existing_url"]
    for r in ctx["readings"]:
        assert r.url != existing_url, f"Duplicate URL was stored: {existing_url}"


@then("the processing log should record one skipped duplicate-url recommendation")
def then_log_records_duplicate_url(bdd_db):
    log = _latest_reading_log(bdd_db)
    md = log.metadata_ or {}
    assert md.get("skipped_duplicate_url") == 1
