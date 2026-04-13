"""Step definitions for profile_update.feature."""

from unittest.mock import AsyncMock, patch

from pytest_bdd import given, scenarios, then, when

from backend.tests.bdd.conftest import (
    create_journal_entry,
    create_onboarding,
    create_triage_item,
    make_topic_extraction_response,
    run_async,
)

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

scenarios("profile_update.feature")


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


@given("onboarding has been completed")
def given_onboarding(bdd_db, ctx):
    state = create_onboarding(bdd_db)
    run_async(bdd_db.commit())
    ctx["onboarding"] = state


@given(
    "I have an unprocessed journal entry with content "
    '"Today I studied Go concurrency patterns including '
    "goroutines, channels, and the select statement. "
    'I also explored mutex usage for shared state."'
)
def given_unprocessed_entry(bdd_db, ctx):
    entry = create_journal_entry(
        bdd_db,
        title="Go Concurrency Study",
        content=(
            "Today I studied Go concurrency patterns including goroutines, channels, "
            "and the select statement. I also explored mutex usage for shared state."
        ),
    )
    run_async(bdd_db.commit())
    ctx["entry"] = entry


@when("the nightly profile update pipeline runs")
def when_profile_update(bdd_db, ctx):
    from backend.app.pipelines.profile_update import run_profile_update

    mock_response = make_topic_extraction_response()

    with patch(
        "backend.app.pipelines.profile_update.llm_client.chat_completion_json",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = run_async(run_profile_update(bdd_db))
        run_async(bdd_db.commit())

    ctx["pipeline_result"] = result


@then("the pipeline should complete successfully")
def then_pipeline_completed(ctx):
    assert ctx["pipeline_result"]["status"] == "completed"


@then("new topics should appear in the Knowledge Profile")
def then_topics_appear(bdd_client):
    resp = run_async(bdd_client.get("/api/v1/profile"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_topics"] > 0


@then("the journal entry should be marked as processed")
def then_entry_processed(ctx):
    assert ctx["pipeline_result"]["entries_processed"] >= 1


@then("a profile snapshot should be created")
def then_snapshot_created(bdd_client):
    resp = run_async(bdd_client.get("/api/v1/profile/snapshots"))
    assert resp.status_code == 200
    assert len(resp.json()) > 0


# --- No new entries scenario ------------------------------------------------


@then("the pipeline should report no new entries")
def then_no_new_entries(ctx):
    assert ctx["pipeline_result"]["status"] == "no_new_entries"


# --- Blocking triage scenario -----------------------------------------------


@given("there is a critical unresolved triage item")
def given_critical_triage(bdd_db, ctx):
    item = create_triage_item(bdd_db, severity="critical")
    run_async(bdd_db.commit())
    ctx["triage_item"] = item


@then("the pipeline should be blocked by triage")
def then_blocked(ctx):
    assert ctx["pipeline_result"]["status"] == "blocked"
