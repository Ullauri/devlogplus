"""Step definitions for project_lifecycle.feature."""

import os
from unittest.mock import AsyncMock, patch

from pytest_bdd import given, parsers, scenarios, then, when

from backend.tests.bdd.conftest import (
    create_onboarding,
    create_project,
    create_topics,
    make_project_evaluation_response,
    make_project_generation_response,
    run_async,
)

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

scenarios("project_lifecycle.feature")


# ---------------------------------------------------------------------------
# Background steps
# ---------------------------------------------------------------------------


@given(parsers.parse('onboarding has been completed with go experience "{level}"'))
def given_onboarding_with_level(bdd_db, ctx, level):
    state = create_onboarding(bdd_db, go_level=level)
    run_async(bdd_db.commit())
    ctx["onboarding"] = state


@given("the Knowledge Profile has topics")
def given_topics(bdd_db, ctx):
    topics = create_topics(bdd_db)
    run_async(bdd_db.commit())
    ctx["topics"] = topics


# ---------------------------------------------------------------------------
# Generate project
# ---------------------------------------------------------------------------


@when("the project generation pipeline runs")
def when_generate_project(bdd_db, ctx):
    from backend.app.pipelines.project_pipeline import generate_project

    mock_response = make_project_generation_response()

    with patch(
        "backend.app.pipelines.project_pipeline.llm_client.chat_completion_json",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        project = run_async(generate_project(bdd_db))
        run_async(bdd_db.commit())

    ctx["project"] = project


@then(parsers.parse('a new project should be created with status "{status}"'))
def then_project_status(ctx, status):
    assert ctx["project"].status.value == status


@then("the project should have tasks")
def then_project_has_tasks(bdd_client, ctx):
    project_id = str(ctx["project"].id)
    resp = run_async(bdd_client.get(f"/api/v1/projects/{project_id}"))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tasks"]) > 0


@then("the project files should be written to disk")
def then_files_on_disk(ctx):
    project_path = ctx["project"].project_path
    assert os.path.isdir(project_path)
    # Clean up test files
    ctx["_project_path_cleanup"] = project_path


# ---------------------------------------------------------------------------
# Submit project
# ---------------------------------------------------------------------------


@given(parsers.parse('a project exists with status "{status}"'))
def given_project(bdd_db, ctx, status):
    project = create_project(bdd_db, status=status)
    run_async(bdd_db.commit())
    ctx["project"] = project


@when(parsers.parse('I submit the project with notes "{notes}"'))
def when_submit_project(bdd_client, ctx, notes):
    project_id = str(ctx["project"].id)
    resp = run_async(
        bdd_client.post(
            f"/api/v1/projects/{project_id}/submit",
            json={"notes": notes},
        )
    )
    ctx["submit_response"] = resp
    ctx["submitted_project"] = resp.json()


@then(parsers.parse('the project status should be "{status}"'))
def then_status(ctx, status):
    assert ctx["submitted_project"]["status"] == status


# ---------------------------------------------------------------------------
# Evaluate project
# ---------------------------------------------------------------------------


@given("a submitted project exists with code on disk")
def given_submitted_project(bdd_db, ctx):
    project = create_project(bdd_db, status="submitted", with_files=True)
    run_async(bdd_db.commit())
    ctx["project"] = project
    ctx["project_id"] = str(project.id)


@when("the project evaluation pipeline runs")
def when_evaluate_project(bdd_db, ctx):
    from backend.app.pipelines.project_pipeline import evaluate_project

    project_id = ctx["project"].id
    mock_response = make_project_evaluation_response()

    with patch(
        "backend.app.pipelines.project_pipeline.llm_client.chat_completion_json",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = run_async(evaluate_project(bdd_db, project_id))
        run_async(bdd_db.commit())

    # Expire cached objects so the API re-fetches with relationships
    bdd_db.expire_all()

    ctx["eval_result"] = result


@then("the project should have an evaluation")
def then_has_evaluation(bdd_client, ctx):
    project_id = ctx["project_id"]
    resp = run_async(bdd_client.get(f"/api/v1/projects/{project_id}"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["evaluation"] is not None
    ctx["submitted_project"] = body


@then("the evaluation should include a code quality score")
def then_quality_score(ctx):
    assert ctx["eval_result"]["code_quality"] > 0
