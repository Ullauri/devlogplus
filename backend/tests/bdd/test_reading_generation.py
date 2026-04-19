"""Step definitions for reading_generation.feature."""

from unittest.mock import AsyncMock, patch

from pytest_bdd import given, parsers, scenarios, then, when

from backend.tests.bdd.conftest import (
    create_allowlist_entries,
    create_onboarding,
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


@then("the processing log should record the skipped URL")
def then_log_records_skipped(bdd_db, ctx):
    from sqlalchemy import select

    from backend.app.models.base import PipelineType
    from backend.app.models.settings import ProcessingLog

    stmt = (
        select(ProcessingLog)
        .where(ProcessingLog.pipeline == PipelineType.READING_GENERATION)
        .order_by(ProcessingLog.started_at.desc())
        .limit(1)
    )
    log = run_async(bdd_db.execute(stmt)).scalar_one()
    skipped = (log.metadata_ or {}).get("skipped_unreachable", [])
    assert any("blog.golang.org/pipelines" in s.get("url", "") for s in skipped)
