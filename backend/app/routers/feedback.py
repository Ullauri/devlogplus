"""Feedback API — thumbs up/down and feedforward notes on generated items."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.schemas.feedback import FeedbackCreate, FeedbackResponse
from backend.app.services import feedback as feedback_svc

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=201,
    summary="Submit feedback or feedforward",
    response_description="The recorded feedback entry",
    responses={422: {"description": "Validation error — target_type and target_id are required"}},
)
async def create_feedback(
    data: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    """Submit feedback and/or feedforward on a generated item.

    Two distinct signal types are supported:

    - **Feedback** (`reaction`) — a thumbs-up or thumbs-down that corrects
      the system's current understanding (e.g. “too easy”, “not relevant”).
    - **Feedforward** (`note`) — free-text that shapes what the system should
      generate next (e.g. “more backend-oriented content”).

    At least one of `reaction` or `note` should be provided.
    """
    fb = await feedback_svc.create_feedback(db, data)
    return FeedbackResponse.model_validate(fb)


@router.get(
    "",
    response_model=list[FeedbackResponse],
    summary="List feedback",
    response_description="Paginated list of all feedback entries, most recent first",
)
async def list_feedback(
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    limit: int = Query(50, ge=1, le=200, description="Maximum entries to return"),
    db: AsyncSession = Depends(get_db),
) -> list[FeedbackResponse]:
    """Return all feedback entries ordered by creation date (most recent first)."""
    items = await feedback_svc.list_all_feedback(db, offset=offset, limit=limit)
    return [FeedbackResponse.model_validate(f) for f in items]
