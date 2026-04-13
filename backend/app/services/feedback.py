"""Feedback service — feedback and feedforward on generated items."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import FeedbackTargetType
from backend.app.models.feedback import Feedback
from backend.app.schemas.feedback import FeedbackCreate


async def create_feedback(db: AsyncSession, data: FeedbackCreate) -> Feedback:
    """Record feedback (thumbs up/down) and/or feedforward (text note) on an item."""
    fb = Feedback(
        target_type=data.target_type,
        target_id=data.target_id,
        reaction=data.reaction,
        note=data.note,
    )
    db.add(fb)
    await db.flush()
    return fb


async def list_feedback_for_target(
    db: AsyncSession,
    target_type: FeedbackTargetType,
    target_id: uuid.UUID,
) -> list[Feedback]:
    """Get all feedback for a specific item."""
    stmt = (
        select(Feedback)
        .where(Feedback.target_type == target_type, Feedback.target_id == target_id)
        .order_by(Feedback.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_all_feedback(
    db: AsyncSession, *, offset: int = 0, limit: int = 50
) -> list[Feedback]:
    """List all feedback (most recent first)."""
    stmt = select(Feedback).order_by(Feedback.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
