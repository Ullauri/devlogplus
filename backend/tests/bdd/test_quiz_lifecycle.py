"""Step definitions for quiz_lifecycle.feature."""

from unittest.mock import AsyncMock, patch

from pytest_bdd import given, parsers, scenarios, then, when

from backend.tests.bdd.conftest import (
    create_feedback,
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


# ---------------------------------------------------------------------------
# Helper: load the most recent quiz-generation processing log
# ---------------------------------------------------------------------------


def _latest_quiz_gen_log(bdd_db):
    from sqlalchemy import select

    from backend.app.models.base import PipelineType
    from backend.app.models.settings import ProcessingLog

    stmt = (
        select(ProcessingLog)
        .where(ProcessingLog.pipeline == PipelineType.QUIZ_GENERATION)
        .order_by(ProcessingLog.started_at.desc())
        .limit(1)
    )
    return run_async(bdd_db.execute(stmt)).scalar_one()


# ---------------------------------------------------------------------------
# Thumbs-up loop prevention scenario
# ---------------------------------------------------------------------------


@given(parsers.parse('a previously asked question "{question_text}" has been thumbs-upped'))
def given_thumbs_upped_question(bdd_db, ctx, question_text):
    from sqlalchemy import select

    from backend.app.models.quiz import QuizQuestion

    # Reuse the seeded session helper, then thumbs-up its first question
    # (which has text "Explain goroutines.").
    session = create_quiz_session(bdd_db, status="evaluated")
    run_async(bdd_db.commit())
    # Fetch the question via an explicit async query — the `session.questions`
    # relationship is lazy and would trigger a MissingGreenlet from sync code.
    stmt = select(QuizQuestion).where(
        QuizQuestion.session_id == session.id,
        QuizQuestion.question_text == question_text,
    )
    target_q = run_async(bdd_db.execute(stmt)).scalar_one()
    create_feedback(
        bdd_db,
        target_type="quiz_question",
        target_id=target_q.id,
        reaction="thumbs_up",
    )
    run_async(bdd_db.commit())
    ctx["liked_question_text"] = question_text
    ctx["liked_question"] = target_q


@when("the quiz generation pipeline runs and proposes that same question again")
def when_quiz_proposes_liked_question(bdd_db, ctx):
    from backend.app.pipelines.quiz_pipeline import generate_quiz

    liked_text = ctx["liked_question_text"]
    # LLM proposes the liked question verbatim, plus one fresh question on a
    # different topic so the session isn't entirely empty after filtering.
    mock_response = make_quiz_generation_response(
        questions=[
            {
                "question_text": liked_text,
                "question_type": "reinforcement",
                "target_topic": "Go concurrency patterns",
                "difficulty_rationale": "LLM didn't realise it asked this before",
            },
            {
                "question_text": "How do you wrap errors in Go without losing the original?",
                "question_type": "exploration",
                "target_topic": "Go error handling",
                "difficulty_rationale": "Different topic, fresh question",
            },
        ]
    )

    with patch(
        "backend.app.pipelines.quiz_pipeline.llm_client.chat_completion_json",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        session = run_async(generate_quiz(bdd_db))
        run_async(bdd_db.commit())

    ctx["new_session"] = session


@then("the previously-liked question should not appear in the new session")
def then_liked_question_excluded(bdd_db, ctx):
    from sqlalchemy import select

    from backend.app.models.quiz import QuizQuestion

    new_session = ctx["new_session"]
    liked_text = ctx["liked_question_text"]
    stmt = select(QuizQuestion).where(QuizQuestion.session_id == new_session.id)
    rows = run_async(bdd_db.execute(stmt)).scalars().all()
    texts = {q.question_text for q in rows}
    assert liked_text not in texts
    assert len(rows) == 1


@then("the processing log should record one skipped already-liked question")
def then_quiz_log_records_already_liked(bdd_db):
    log = _latest_quiz_gen_log(bdd_db)
    assert (log.metadata_ or {}).get("skipped_already_liked") == 1


# ---------------------------------------------------------------------------
# Diversity dedupe scenario
# ---------------------------------------------------------------------------


@when("the quiz generation pipeline runs with two questions targeting the same topic")
def when_quiz_two_same_topic(bdd_db, ctx):
    from backend.app.pipelines.quiz_pipeline import generate_quiz

    # Both questions share target_topic; the *only* reason the second
    # should be dropped is the diversity gate.
    mock_response = make_quiz_generation_response(
        questions=[
            {
                "question_text": "Explain how Go channels coordinate goroutines.",
                "question_type": "reinforcement",
                "target_topic": "Go concurrency patterns",
                "difficulty_rationale": "Core concept",
            },
            {
                "question_text": "What are buffered vs unbuffered channel trade-offs?",
                "question_type": "exploration",
                "target_topic": "Go concurrency patterns",
                "difficulty_rationale": "Same topic — diversity gate should drop this",
            },
        ]
    )

    with patch(
        "backend.app.pipelines.quiz_pipeline.llm_client.chat_completion_json",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        session = run_async(generate_quiz(bdd_db))
        run_async(bdd_db.commit())

    ctx["new_session"] = session


@then("only one question should be stored for that topic")
def then_one_question_per_topic(bdd_db, ctx):
    from sqlalchemy import select

    from backend.app.models.quiz import QuizQuestion

    new_session = ctx["new_session"]
    stmt = select(QuizQuestion).where(QuizQuestion.session_id == new_session.id)
    rows = run_async(bdd_db.execute(stmt)).scalars().all()
    assert len(rows) == 1
    ctx["stored_question_count"] = len(rows)


@then("the session question_count should match the number of stored questions")
def then_session_count_matches(bdd_db, ctx):
    # Re-fetch the session to get the post-commit value.
    from sqlalchemy import select

    from backend.app.models.quiz import QuizSession

    new_session = ctx["new_session"]
    stmt = select(QuizSession).where(QuizSession.id == new_session.id)
    refreshed = run_async(bdd_db.execute(stmt)).scalar_one()
    assert refreshed.question_count == ctx["stored_question_count"] == 1


@then("the processing log should record one skipped duplicate-topic question")
def then_quiz_log_records_duplicate_topic(bdd_db):
    log = _latest_quiz_gen_log(bdd_db)
    md = log.metadata_ or {}
    assert md.get("skipped_duplicate_topic") == 1
    assert md.get("distinct_topics") == 1
