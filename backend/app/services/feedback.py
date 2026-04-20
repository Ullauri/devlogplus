"""Feedback service — feedback and feedforward on generated items."""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import FeedbackReaction, FeedbackTargetType
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


async def list_feedback_by_target_types(
    db: AsyncSession,
    target_types: Iterable[FeedbackTargetType],
    *,
    limit: int = 50,
) -> list[Feedback]:
    """List recent feedback whose ``target_type`` is in the given set (most recent first)."""
    types_list = list(target_types)
    if not types_list:
        return []
    stmt = (
        select(Feedback)
        .where(Feedback.target_type.in_(types_list))
        .order_by(Feedback.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_disliked_target_ids(
    db: AsyncSession, target_type: FeedbackTargetType
) -> set[uuid.UUID]:
    """Return the set of target IDs that received a ``thumbs_down`` reaction.

    Used by generation pipelines to avoid recommending items the user has
    already rejected.
    """
    stmt = select(Feedback.target_id).where(
        Feedback.target_type == target_type,
        Feedback.reaction == FeedbackReaction.THUMBS_DOWN,
    )
    result = await db.execute(stmt)
    return {row for row in result.scalars().all()}


async def list_liked_target_ids(
    db: AsyncSession, target_type: FeedbackTargetType
) -> set[uuid.UUID]:
    """Return the set of target IDs that received a ``thumbs_up`` reaction.

    Used by generation pipelines to learn what kinds of items the user has
    responded positively to, so future recommendations can lean in the same
    *direction* (topic / domain / type) without re-recommending the exact
    same item.
    """
    stmt = select(Feedback.target_id).where(
        Feedback.target_type == target_type,
        Feedback.reaction == FeedbackReaction.THUMBS_UP,
    )
    result = await db.execute(stmt)
    return {row for row in result.scalars().all()}
