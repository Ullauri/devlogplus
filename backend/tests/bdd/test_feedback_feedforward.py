"""Step definitions for feedback_feedforward.feature."""

from pytest_bdd import given, parsers, scenarios, then, when

from backend.tests.bdd.conftest import (
    create_project,
    create_quiz_session,
    run_async,
)

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

scenarios("feedback_feedforward.feature")


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


@given("a quiz session exists with questions")
def given_quiz(bdd_db, ctx):
    session = create_quiz_session(bdd_db, status="pending")
    run_async(bdd_db.commit())
    ctx["quiz_session"] = session


@when("I submit thumbs-up feedback for the first question")
def when_thumbs_up(bdd_client, ctx):
    session_id = str(ctx["quiz_session"].id)
    resp = run_async(bdd_client.get(f"/api/v1/quizzes/sessions/{session_id}"))
    assert resp.status_code == 200
    questions = resp.json()["questions"]
    first_q_id = questions[0]["id"]

    fb_resp = run_async(
        bdd_client.post(
            "/api/v1/feedback",
            json={
                "target_type": "quiz_question",
                "target_id": first_q_id,
                "reaction": "thumbs_up",
            },
        )
    )
    ctx["feedback_response"] = fb_resp
    ctx["feedback"] = fb_resp.json()


@then(parsers.parse('the feedback should be recorded with reaction "{reaction}"'))
def then_reaction(ctx, reaction):
    assert ctx["feedback_response"].status_code == 201
    assert ctx["feedback"]["reaction"] == reaction


# --- Project feedforward scenario -------------------------------------------


@given("a project exists")
def given_project(bdd_db, ctx):
    project = create_project(bdd_db, status="issued")
    run_async(bdd_db.commit())
    ctx["project"] = project


@when(parsers.parse('I submit feedback with note "{note}" for the project'))
def when_feedforward(bdd_client, ctx, note):
    project_id = str(ctx["project"].id)
    fb_resp = run_async(
        bdd_client.post(
            "/api/v1/feedback",
            json={
                "target_type": "project",
                "target_id": project_id,
                "note": note,
            },
        )
    )
    ctx["feedback_response"] = fb_resp
    ctx["feedback"] = fb_resp.json()


@then("the feedback should be recorded with the feedforward note")
def then_feedforward_note(ctx):
    assert ctx["feedback_response"].status_code == 201
    assert ctx["feedback"]["note"] is not None


# --- Feedback list scenario -------------------------------------------------


@given(parsers.parse('I have submitted feedback with note "{note}"'))
def given_feedback_exists(bdd_db, bdd_client, ctx):
    from backend.tests.bdd.conftest import create_project

    project = create_project(bdd_db, status="issued")
    run_async(bdd_db.commit())

    project_id = str(project.id)
    fb_resp = run_async(
        bdd_client.post(
            "/api/v1/feedback",
            json={
                "target_type": "project",
                "target_id": project_id,
                "note": "harder debugging tasks",
            },
        )
    )
    assert fb_resp.status_code == 201
    ctx["feedback"] = fb_resp.json()


@when("I list all feedback")
def when_list_feedback(bdd_client, ctx):
    resp = run_async(bdd_client.get("/api/v1/feedback"))
    assert resp.status_code == 200
    ctx["feedback_list"] = resp.json()


@then(parsers.parse('the feedforward note "{note}" should be present'))
def then_note_present(ctx, note):
    notes = [f["note"] for f in ctx["feedback_list"] if f.get("note")]
    assert note in notes
