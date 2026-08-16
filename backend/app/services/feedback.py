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


async def latest_reactions(
    db: AsyncSession, target_type: FeedbackTargetType
) -> dict[uuid.UUID, FeedbackReaction | None]:
    """Return each target's *current* reaction — the most recent one recorded.

    Feedback is an append-only log: every click writes a new row, and clearing
    a reaction writes a row with ``reaction = NULL``. Reading the whole log and
    matching on reaction value therefore answers "was this ever thumbs-downed",
    not "is this thumbs-downed", which are different questions once a user
    changes their mind. It produced two live defects: a cleared reaction was
    still honoured forever, and an item rated up and later down appeared in the
    liked *and* disliked sets at once, steering the next batch both ways.

    ``DISTINCT ON`` collapses the log to one row per target. ``created_at`` is
    ``now()``, i.e. transaction-start time, so rows written in one transaction
    tie; ``id`` then breaks the tie to keep the result deterministic rather
    than correct — which is sound here because each click is its own request
    and therefore its own transaction.
    """
    stmt = (
        select(Feedback.target_id, Feedback.reaction)
        .where(Feedback.target_type == target_type)
        .distinct(Feedback.target_id)
        .order_by(Feedback.target_id, Feedback.created_at.desc(), Feedback.id.desc())
    )
    result = await db.execute(stmt)
    return {target_id: reaction for target_id, reaction in result.all()}


async def list_disliked_target_ids(
    db: AsyncSession, target_type: FeedbackTargetType
) -> set[uuid.UUID]:
    """Return target IDs whose *current* reaction is ``thumbs_down``.

    Used by generation pipelines to avoid recommending items the user has
    rejected. See ``latest_reactions`` for why "current" rather than "ever".
    """
    reactions = await latest_reactions(db, target_type)
    return {tid for tid, r in reactions.items() if r == FeedbackReaction.THUMBS_DOWN}


async def list_liked_target_ids(
    db: AsyncSession, target_type: FeedbackTargetType
) -> set[uuid.UUID]:
    """Return target IDs whose *current* reaction is ``thumbs_up``.

    Used by generation pipelines to learn what kinds of items the user has
    responded positively to, so future recommendations can lean in the same
    *direction* (topic / domain / type) without re-recommending the exact
    same item.
    """
    reactions = await latest_reactions(db, target_type)
    return {tid for tid, r in reactions.items() if r == FeedbackReaction.THUMBS_UP}
