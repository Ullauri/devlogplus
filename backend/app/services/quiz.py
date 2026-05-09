"""Quiz service — session management, answer submission, evaluation retrieval."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.base import QuizSessionStatus
from backend.app.models.quiz import QuizAnswer, QuizQuestion, QuizSession
from backend.app.schemas.quiz import QuizAnswerCreate


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> QuizSession | None:
    """Get a quiz session with all questions, answers, and evaluations."""
    stmt = (
        select(QuizSession)
        .options(
            selectinload(QuizSession.questions).selectinload(QuizQuestion.answer),
            selectinload(QuizSession.questions).selectinload(QuizQuestion.evaluation),
            selectinload(QuizSession.questions).selectinload(QuizQuestion.topic),
        )
        .where(QuizSession.id == session_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_sessions(db: AsyncSession, *, offset: int = 0, limit: int = 20) -> list[QuizSession]:
    """List quiz sessions (most recent first)."""
    stmt = select(QuizSession).order_by(QuizSession.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_current_session(db: AsyncSession) -> QuizSession | None:
    """Get the most recent non-evaluated session (if any)."""
    stmt = (
        select(QuizSession)
        .options(
            selectinload(QuizSession.questions).selectinload(QuizQuestion.answer),
            selectinload(QuizSession.questions).selectinload(QuizQuestion.evaluation),
            selectinload(QuizSession.questions).selectinload(QuizQuestion.topic),
        )
        .where(QuizSession.status.in_([QuizSessionStatus.PENDING, QuizSessionStatus.IN_PROGRESS]))
        .order_by(QuizSession.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


class AnswerAlreadyExistsError(Exception):
    """Raised when an answer already exists for a question."""


async def submit_answer(
    db: AsyncSession,
    question_id: uuid.UUID,
    data: QuizAnswerCreate,
) -> QuizAnswer | None:
    """Submit an answer to a quiz question.

    Returns None if the question does not exist.
    Raises AnswerAlreadyExistsError if the question already has an answer.
    """
    # Verify the question exists
    stmt = select(QuizQuestion).where(QuizQuestion.id == question_id)
    result = await db.execute(stmt)
    question = result.scalar_one_or_none()
    if question is None:
        return None

    # Guard against duplicate submissions (question_id has a UNIQUE constraint)
    existing_stmt = select(QuizAnswer).where(QuizAnswer.question_id == question_id)
    existing_result = await db.execute(existing_stmt)
    if existing_result.scalar_one_or_none() is not None:
        raise AnswerAlreadyExistsError(question_id)

    answer = QuizAnswer(
        question_id=question_id,
        answer_text=data.answer_text,
    )
    db.add(answer)

    # Update session status to in_progress if it was pending
    session_stmt = select(QuizSession).where(QuizSession.id == question.session_id)
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    if session and session.status == QuizSessionStatus.PENDING:
        session.status = QuizSessionStatus.IN_PROGRESS

    await db.flush()
    return answer


async def complete_session(db: AsyncSession, session_id: uuid.UUID) -> QuizSession | None:
    """Mark a quiz session as completed (all answers submitted)."""
    session = await get_session(db, session_id)
    if session is None:
        return None

    session.status = QuizSessionStatus.COMPLETED
    session.completed_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(session)
    return await get_session(db, session_id)  # type: ignore[return-value]
