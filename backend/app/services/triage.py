"""Triage service — manage items requiring user attention."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from backend.app.models.base import TriageSeverity, TriageStatus
from backend.app.models.triage import TriageItem
from backend.app.schemas.triage import TriageResolveRequest


async def list_triage_items(
    db: AsyncSession,
    *,
    status: TriageStatus | None = None,
    severity: TriageSeverity | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[TriageItem]:
    """List triage items with optional filters."""
    stmt = select(TriageItem).order_by(
        # Critical first, then by recency
        TriageItem.severity.desc(),
        TriageItem.created_at.desc(),
    )
    if status is not None:
        stmt = stmt.where(TriageItem.status == status)
    if severity is not None:
        stmt = stmt.where(TriageItem.severity == severity)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_triage_items(
    db: AsyncSession,
    *,
    status: TriageStatus | None = None,
    severity: TriageSeverity | None = None,
) -> int:
    """Return the total number of triage items matching the given filters."""
    stmt = select(count(TriageItem.id))
    if status is not None:
        stmt = stmt.where(TriageItem.status == status)
    if severity is not None:
        stmt = stmt.where(TriageItem.severity == severity)
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def get_triage_item(db: AsyncSession, item_id: uuid.UUID) -> TriageItem | None:
    """Get a single triage item."""
    stmt = select(TriageItem).where(TriageItem.id == item_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def resolve_triage_item(
    db: AsyncSession, item_id: uuid.UUID, data: TriageResolveRequest
) -> TriageItem | None:
    """Resolve a triage item with a user action."""
    item = await get_triage_item(db, item_id)
    if item is None:
        return None

    item.status = data.action
    item.resolution_text = data.resolution_text
    item.resolved_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(item)
    return item


async def has_blocking_triage(db: AsyncSession) -> bool:
    """Check if there are unresolved high/critical triage items blocking the next cycle."""
    stmt = (
        select(TriageItem.id)
        .where(
            TriageItem.status == TriageStatus.PENDING,
            TriageItem.severity.in_([TriageSeverity.HIGH, TriageSeverity.CRITICAL]),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None
