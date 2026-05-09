"""Tests for the quiz API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import QuizQuestionType, QuizSessionStatus
from backend.app.models.quiz import QuizQuestion, QuizSession

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_quiz_session(db: AsyncSession, *, num_questions: int = 2) -> QuizSession:
    """Helper to create a quiz session with questions."""
    session = QuizSession(status=QuizSessionStatus.PENDING, question_count=num_questions)
    db.add(session)
    await db.flush()

    for i in range(num_questions):
        q = QuizQuestion(
            session_id=session.id,
            question_text=f"What is concept {i + 1}?",
            question_type=QuizQuestionType.REINFORCEMENT,
            order_index=i,
        )
        db.add(q)
    await db.commit()
    await db.refresh(session)
    return session


async def test_list_sessions_empty(client: AsyncClient):
    """Empty list when no quiz sessions exist."""
    resp = await client.get("/api/v1/quizzes/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_current_session_none(client: AsyncClient):
    """No current session when none exist."""
    resp = await client.get("/api/v1/quizzes/sessions/current")
    assert resp.status_code == 200
    # null response
    assert resp.json() is None


async def test_get_session_not_found(client: AsyncClient):
    """Nonexistent session returns 404."""
    resp = await client.get("/api/v1/quizzes/sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_get_session_detail(client: AsyncClient, db_session: AsyncSession):
    """Get a quiz session with its questions."""
    session = await _create_quiz_session(db_session)
    resp = await client.get(f"/api/v1/quizzes/sessions/{session.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert len(data["questions"]) == 2


async def test_get_current_session(client: AsyncClient, db_session: AsyncSession):
    """Current session returns the most recent pending session."""
    _session = await _create_quiz_session(db_session)
    resp = await client.get("/api/v1/quizzes/sessions/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data is not None
    assert data["status"] in ("pending", "in_progress")


async def test_submit_answer(client: AsyncClient, db_session: AsyncSession):
    """Submit an answer to a quiz question."""
    session = await _create_quiz_session(db_session, num_questions=1)

    # Get the question ID from the session detail
    detail_resp = await client.get(f"/api/v1/quizzes/sessions/{session.id}")
    question_id = detail_resp.json()["questions"][0]["id"]

    resp = await client.post(
        f"/api/v1/quizzes/questions/{question_id}/answer",
        json={"answer_text": "Concept 1 is about abstraction."},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["answer_text"] == "Concept 1 is about abstraction."
    assert data["question_id"] == question_id


async def test_submit_answer_not_found(client: AsyncClient):
    """Answering a nonexistent question returns 404."""
    resp = await client.post(
        "/api/v1/quizzes/questions/00000000-0000-0000-0000-000000000000/answer",
        json={"answer_text": "something"},
    )
    assert resp.status_code == 404


async def test_complete_session(client: AsyncClient, db_session: AsyncSession):
    """Mark a quiz session as completed."""
    session = await _create_quiz_session(db_session)
    resp = await client.post(f"/api/v1/quizzes/sessions/{session.id}/complete")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["completed_at"] is not None


async def test_complete_session_not_found(client: AsyncClient):
    """Completing a nonexistent session returns 404."""
    resp = await client.post(
        "/api/v1/quizzes/sessions/00000000-0000-0000-0000-000000000000/complete"
    )
    assert resp.status_code == 404


async def test_submit_duplicate_answer_returns_409(client: AsyncClient, db_session: AsyncSession):
    """Submitting an answer to an already-answered question returns 409, not 500."""
    session = await _create_quiz_session(db_session, num_questions=1)

    detail_resp = await client.get(f"/api/v1/quizzes/sessions/{session.id}")
    question_id = detail_resp.json()["questions"][0]["id"]

    first = await client.post(
        f"/api/v1/quizzes/questions/{question_id}/answer",
        json={"answer_text": "First answer."},
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/quizzes/questions/{question_id}/answer",
        json={"answer_text": "Attempted second answer."},
    )
    assert second.status_code == 409
