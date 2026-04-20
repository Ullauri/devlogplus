"""Step definitions for reading_generation.feature."""

from unittest.mock import AsyncMock, patch

from pytest_bdd import given, parsers, scenarios, then, when

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
        ),
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.validate_urls",
            new_callable=AsyncMock,
            return_value={},  # empty → pipeline treats unknown URLs as reachable
        ),
    ):
        readings = run_async(generate_readings(bdd_db))
        run_async(bdd_db.commit())

    ctx["readings"] = readings


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
            "backend.app.pipelines.reading_pipeline.reading_svc.validate_urls",
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
        "https://go.dev/doc/effective_go#concurrency": (True, None),
        "https://blog.golang.org/pipelines": (False, "HTTP 404"),
    }

    with (
        patch(
            "backend.app.pipelines.reading_pipeline.llm_client.chat_completion_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ),
        patch(
            "backend.app.pipelines.reading_pipeline.reading_svc.validate_urls",
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
    skipped = (log.metadata_ or {}).get("skipped_unreachable", [])
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
            "backend.app.pipelines.reading_pipeline.reading_svc.validate_urls",
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
            "backend.app.pipelines.reading_pipeline.reading_svc.validate_urls",
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
