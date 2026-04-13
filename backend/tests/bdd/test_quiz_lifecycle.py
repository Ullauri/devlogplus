"""Step definitions for quiz_lifecycle.feature."""

from unittest.mock import AsyncMock, patch

from pytest_bdd import given, parsers, scenarios, then, when

from backend.tests.bdd.conftest import (
    create_onboarding,
    create_quiz_session,
    create_topics,
    make_quiz_evaluation_response,
    make_quiz_generation_response,
    run_async,
)

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

scenarios("quiz_lifecycle.feature")


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
# Generate quiz
# ---------------------------------------------------------------------------


@when("the quiz generation pipeline runs")
def when_generate_quiz(bdd_db, ctx):
    from backend.app.pipelines.quiz_pipeline import generate_quiz

    mock_response = make_quiz_generation_response()

    with patch(
        "backend.app.pipelines.quiz_pipeline.llm_client.chat_completion_json",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        session = run_async(generate_quiz(bdd_db))
        run_async(bdd_db.commit())

    ctx["quiz_session"] = session


@then(parsers.parse('a new quiz session should be created with status "{status}"'))
def then_quiz_status(ctx, status):
    assert ctx["quiz_session"].status.value == status


@then("the quiz should have questions")
def then_quiz_has_questions(bdd_client, ctx):
    session_id = str(ctx["quiz_session"].id)
    resp = run_async(bdd_client.get(f"/api/v1/quizzes/sessions/{session_id}"))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["questions"]) > 0
    ctx["quiz_detail"] = body


# ---------------------------------------------------------------------------
# Answer & complete
# ---------------------------------------------------------------------------


@given("a quiz session exists with questions")
def given_quiz_session(bdd_db, ctx):
    session = create_quiz_session(bdd_db, status="pending")
    run_async(bdd_db.commit())
    ctx["quiz_session"] = session


@when(
    parsers.parse('I submit an answer "{answer}" for the first question'),
)
def when_submit_answer(bdd_client, ctx, answer):
    session_id = str(ctx["quiz_session"].id)
    # Fetch session to get question IDs
    resp = run_async(bdd_client.get(f"/api/v1/quizzes/sessions/{session_id}"))
    assert resp.status_code == 200
    questions = resp.json()["questions"]
    ctx["questions"] = questions

    first_q_id = questions[0]["id"]
    ans_resp = run_async(
        bdd_client.post(
            f"/api/v1/quizzes/questions/{first_q_id}/answer",
            json={"answer_text": answer},
        )
    )
    ctx["answer_response"] = ans_resp


@then("the answer should be recorded")
def then_answer_recorded(ctx):
    assert ctx["answer_response"].status_code == 201


@then(parsers.parse('the quiz session status should be "{status}"'))
def then_session_status(bdd_client, ctx, status):
    session_id = str(ctx["quiz_session"].id)
    resp = run_async(bdd_client.get(f"/api/v1/quizzes/sessions/{session_id}"))
    assert resp.status_code == 200
    assert resp.json()["status"] == status


@when("I complete the quiz session")
def when_complete_session(bdd_client, ctx):
    session_id = str(ctx["quiz_session"].id)
    resp = run_async(bdd_client.post(f"/api/v1/quizzes/sessions/{session_id}/complete"))
    ctx["complete_response"] = resp


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------


@given("a completed quiz session with answers exists")
def given_completed_quiz(bdd_db, ctx):
    session = create_quiz_session(bdd_db, status="completed", with_answers=True)
    run_async(bdd_db.commit())
    ctx["quiz_session"] = session


@when("the quiz evaluation pipeline runs")
def when_evaluate_quiz(bdd_db, bdd_client, ctx):
    from backend.app.pipelines.quiz_pipeline import evaluate_quiz

    session_id = ctx["quiz_session"].id

    # Get question IDs for the mock response
    resp = run_async(bdd_client.get(f"/api/v1/quizzes/sessions/{str(session_id)}"))
    questions = resp.json()["questions"]
    question_ids = [q["id"] for q in questions]

    mock_response = make_quiz_evaluation_response(question_ids=question_ids)

    with patch(
        "backend.app.pipelines.quiz_pipeline.llm_client.chat_completion_json",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = run_async(evaluate_quiz(bdd_db, session_id))
        run_async(bdd_db.commit())

    ctx["eval_result"] = result


@then("each question should have an evaluation")
def then_questions_evaluated(ctx):
    assert ctx["eval_result"]["evaluations"] >= 1
