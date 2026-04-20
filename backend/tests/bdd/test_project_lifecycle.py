"""Step definitions for project_lifecycle.feature."""

import os
from unittest.mock import AsyncMock, patch

from pytest_bdd import given, parsers, scenarios, then, when

from backend.tests.bdd.conftest import (
    create_feedback,
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


# ---------------------------------------------------------------------------
# Helper: load the most recent project-generation ProcessingLog
# ---------------------------------------------------------------------------


def _latest_project_gen_log(bdd_db):
    from sqlalchemy import select

    from backend.app.models.base import PipelineType
    from backend.app.models.settings import ProcessingLog

    stmt = (
        select(ProcessingLog)
        .where(ProcessingLog.pipeline == PipelineType.PROJECT_GENERATION)
        .order_by(ProcessingLog.started_at.desc())
        .limit(1)
    )
    return run_async(bdd_db.execute(stmt)).scalar_one()


def _run_generate_project_with_response(bdd_db, ctx, mock_response):
    from backend.app.pipelines.project_pipeline import generate_project

    with patch(
        "backend.app.pipelines.project_pipeline.llm_client.chat_completion_json",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        project = run_async(generate_project(bdd_db))
        run_async(bdd_db.commit())

    ctx["project"] = project


# ---------------------------------------------------------------------------
# Title-collision scenario
# ---------------------------------------------------------------------------


@given(parsers.parse('a previously issued project titled "{title}" has been thumbs-upped'))
def given_thumbs_upped_project(bdd_db, ctx, title):
    project = create_project(bdd_db, status="issued", title=title)
    run_async(bdd_db.commit())
    create_feedback(bdd_db, target_type="project", target_id=project.id, reaction="thumbs_up")
    run_async(bdd_db.commit())
    ctx["seeded_project"] = project
    ctx["seeded_project_title"] = title


@when("the project generation pipeline runs and proposes that same title")
def when_generate_with_colliding_title(bdd_db, ctx):
    # The default mock already returns title "Concurrent File Processor",
    # matching the seeded title in the Given step.
    mock = make_project_generation_response()
    _run_generate_project_with_response(bdd_db, ctx, mock)


@then("the project should still be created")
def then_project_created(ctx):
    # A weekly project is issued per run — we log the collision but do not
    # drop the project.
    assert ctx["project"] is not None
    assert ctx["project"].id is not None


@then("the processing log should flag the project title collision")
def then_log_flags_title_collision(bdd_db, ctx):
    log = _latest_project_gen_log(bdd_db)
    md = log.metadata_ or {}
    assert md.get("project_title_collision") is True


# ---------------------------------------------------------------------------
# Duplicate-task diversity scenario
# ---------------------------------------------------------------------------


@when("the project generation pipeline runs with two tasks sharing the same title")
def when_generate_with_duplicate_tasks(bdd_db, ctx):
    mock = make_project_generation_response()
    # Override the tasks list to include a duplicate title (case-insensitive
    # duplicate to exercise the normalization in the gate).
    mock = dict(mock)
    mock["title"] = "A Fresh Project"  # avoid title-collision cross-talk
    mock["tasks"] = [
        {
            "title": "Implement worker pool",
            "description": "First version",
            "task_type": "feature",
        },
        {
            "title": "implement worker pool",  # same title, different case
            "description": "Duplicate — should be dropped by diversity gate",
            "task_type": "refactor",
        },
        {
            "title": "Fix race condition",
            "description": "Fresh task, distinct title",
            "task_type": "bug_fix",
        },
    ]
    _run_generate_project_with_response(bdd_db, ctx, mock)


@then("only one task with that title should be stored")
def then_one_task_per_title(bdd_db, ctx):
    from sqlalchemy import select

    from backend.app.models.project import ProjectTask

    stmt = select(ProjectTask).where(ProjectTask.project_id == ctx["project"].id)
    tasks = run_async(bdd_db.execute(stmt)).scalars().all()
    titles_lower = [t.title.lower() for t in tasks]
    # The two "implement worker pool" tasks should collapse to one.
    assert titles_lower.count("implement worker pool") == 1
    # Total: worker pool + race condition = 2 (one duplicate dropped).
    assert len(tasks) == 2


@then("the processing log should record one skipped duplicate task")
def then_log_records_duplicate_task(bdd_db):
    log = _latest_project_gen_log(bdd_db)
    md = log.metadata_ or {}
    assert md.get("skipped_duplicate_tasks") == 1
    assert md.get("tasks_generated") == 3
    assert md.get("tasks_stored") == 2


# ---------------------------------------------------------------------------
# Reacted-to task title exclusion scenario
# ---------------------------------------------------------------------------


@given(parsers.parse('a previously issued project with a thumbs-upped task titled "{task_title}"'))
def given_thumbs_upped_task(bdd_db, ctx, task_title):
    project = create_project(
        bdd_db,
        status="issued",
        title="Old Project With Liked Task",
        tasks=[(task_title, "bug_fix")],
    )
    run_async(bdd_db.commit())
    # Grab the seeded task (stashed on the project by the factory).
    seeded_task = project._seeded_tasks[0]  # type: ignore[attr-defined]
    create_feedback(
        bdd_db,
        target_type="project_task",
        target_id=seeded_task.id,
        reaction="thumbs_up",
    )
    run_async(bdd_db.commit())
    ctx["liked_task_title"] = task_title


@when("the project generation pipeline runs and proposes that same task title")
def when_generate_with_reacted_task(bdd_db, ctx):
    liked = ctx["liked_task_title"]
    mock = make_project_generation_response()
    mock = dict(mock)
    mock["title"] = "A Brand New Project"  # avoid title-collision cross-talk
    # One task re-proposes the liked title; a second is fresh so the project
    # isn't left with zero tasks after filtering.
    mock["tasks"] = [
        {
            "title": liked,
            "description": "LLM didn't realise the user already did this",
            "task_type": "bug_fix",
        },
        {
            "title": "Add structured logging",
            "description": "Fresh, non-colliding task",
            "task_type": "feature",
        },
    ]
    _run_generate_project_with_response(bdd_db, ctx, mock)


@then("the previously-liked task title should not appear in the new project")
def then_reacted_task_excluded(bdd_db, ctx):
    from sqlalchemy import select

    from backend.app.models.project import ProjectTask

    stmt = select(ProjectTask).where(ProjectTask.project_id == ctx["project"].id)
    tasks = run_async(bdd_db.execute(stmt)).scalars().all()
    titles_lower = {t.title.lower() for t in tasks}
    assert ctx["liked_task_title"].lower() not in titles_lower
    # Only the fresh task survives.
    assert len(tasks) == 1


@then("the processing log should record one skipped reacted-to task")
def then_log_records_avoid_task(bdd_db):
    log = _latest_project_gen_log(bdd_db)
    md = log.metadata_ or {}
    assert md.get("skipped_avoid_tasks") == 1
