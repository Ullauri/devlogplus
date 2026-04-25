"""Quiz API — sessions, questions, answers, and evaluations."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.schemas.quiz import (
    QuizAnswerCreate,
    QuizAnswerResponse,
    QuizSessionDetailResponse,
    QuizSessionResponse,
)
from backend.app.services import quiz as quiz_svc

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.get(
    "/sessions",
    response_model=list[QuizSessionResponse],
    summary="List quiz sessions",
    response_description="Paginated list of quiz sessions, most recent first",
)
async def list_sessions(
    offset: int = Query(0, ge=0, description="Number of sessions to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum sessions to return"),
    db: AsyncSession = Depends(get_db),
) -> list[QuizSessionResponse]:
    """Return quiz sessions ordered by creation date (most recent first).

    Each session represents a weekly quiz with a configurable number of
    free-text questions generated from the Knowledge Profile.
    """
    sessions = await quiz_svc.list_sessions(db, offset=offset, limit=limit)
    return [QuizSessionResponse.model_validate(s) for s in sessions]


@router.get(
    "/sessions/current",
    response_model=QuizSessionDetailResponse | None,
    summary="Get current quiz session",
    response_description="The active quiz session with questions, or null if none exists",
)
async def get_current_session(
    db: AsyncSession = Depends(get_db),
) -> QuizSessionDetailResponse | None:
    """Get the active (non-evaluated) quiz session, if any.

    Returns `null` when there is no pending session.  A new session is
    generated weekly by the quiz pipeline.
    """
    session = await quiz_svc.get_current_session(db)
    if session is None:
        return None
    return QuizSessionDetailResponse.model_validate(session)


@router.get(
    "/sessions/{session_id}",
    response_model=QuizSessionDetailResponse,
    summary="Get quiz session details",
    response_description="Quiz session with all questions, answers, and evaluations",
    responses={404: {"description": "Quiz session not found"}},
)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> QuizSessionDetailResponse:
    """Retrieve a specific quiz session with its questions, submitted answers,
    and LLM-generated evaluations.

    Evaluations include correctness (full / partial / incorrect), depth
    assessment, explanation, and confidence score.
    """
    session = await quiz_svc.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Quiz session not found")
    return QuizSessionDetailResponse.model_validate(session)


@router.post(
    "/questions/{question_id}/answer",
    response_model=QuizAnswerResponse,
    status_code=201,
    summary="Submit quiz answer",
    response_description="The recorded answer",
    responses={
        404: {"description": "Quiz question not found"},
        422: {"description": "Validation error — answer_text is required"},
    },
)
async def submit_answer(
    question_id: uuid.UUID,
    data: QuizAnswerCreate,
    db: AsyncSession = Depends(get_db),
) -> QuizAnswerResponse:
    """Submit a free-text answer to a quiz question.

    Only free-text answers are accepted (no multiple choice).  Each question
    can only be answered once.  The answer will be evaluated by an LLM judge
    when the session is completed.
    """
    answer = await quiz_svc.submit_answer(db, question_id, data)
    if answer is None:
        raise HTTPException(status_code=404, detail="Quiz question not found")
    return QuizAnswerResponse.model_validate(answer)


@router.post(
    "/sessions/{session_id}/complete",
    response_model=QuizSessionResponse,
    summary="Complete quiz session",
    response_description="The completed quiz session",
    responses={404: {"description": "Quiz session not found"}},
)
async def complete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> QuizSessionResponse:
    """Mark a quiz session as completed.

    All answers should be submitted before completing.  Once completed, use
    the quiz evaluation endpoint to assess answers and update the Knowledge
    Profile.
    """
    session = await quiz_svc.complete_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Quiz session not found")
    return QuizSessionResponse.model_validate(session)
