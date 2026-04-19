"""Feedback API — thumbs up/down and feedforward notes on generated items."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models.base import FeedbackTargetType
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
    response_description=(
        "Feedback entries, most recent first. When both target_type and "
        "target_id are provided, only entries for that item are returned."
    ),
)
async def list_feedback(
    target_type: FeedbackTargetType | None = Query(
        None,
        description="Restrict results to feedback on items of this type.",
    ),
    target_id: uuid.UUID | None = Query(
        None,
        description="Restrict results to a single item. Requires target_type.",
    ),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    limit: int = Query(50, ge=1, le=200, description="Maximum entries to return"),
    db: AsyncSession = Depends(get_db),
) -> list[FeedbackResponse]:
    """Return feedback entries ordered by creation date (most recent first).

    If both ``target_type`` and ``target_id`` are supplied, the result is
    narrowed to feedback on that specific item — this is how the UI hydrates
    previously submitted reactions/notes when rendering generated items.
    """
    if target_type is not None and target_id is not None:
        items = await feedback_svc.list_feedback_for_target(db, target_type, target_id)
    else:
        items = await feedback_svc.list_all_feedback(db, offset=offset, limit=limit)
    return [FeedbackResponse.model_validate(f) for f in items]
