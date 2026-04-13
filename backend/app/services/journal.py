"""Journal service — CRUD with append-only versioning."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.journal import JournalEntry, JournalEntryVersion
from backend.app.schemas.journal import (
    JournalEntryCreate,
    JournalEntryResponse,
    JournalEntryUpdate,
)


async def create_entry(db: AsyncSession, data: JournalEntryCreate) -> JournalEntry:
    """Create a new journal entry with its initial version."""
    entry = JournalEntry(title=data.title)
    db.add(entry)
    await db.flush()

    version = JournalEntryVersion(
        entry_id=entry.id,
        content=data.content,
        version_number=1,
        is_current=True,
    )
    db.add(version)
    await db.flush()

    # Reload with versions eagerly loaded
    return await get_entry(db, entry.id)  # type: ignore[return-value]


async def get_entry(db: AsyncSession, entry_id: uuid.UUID) -> JournalEntry | None:
    """Get a single journal entry with all versions."""
    stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.versions))
        .where(JournalEntry.id == entry_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_entries(db: AsyncSession, *, offset: int = 0, limit: int = 50) -> list[JournalEntry]:
    """List journal entries (most recent first)."""
    stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.versions))
        .order_by(JournalEntry.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_entry(
    db: AsyncSession, entry_id: uuid.UUID, data: JournalEntryUpdate
) -> JournalEntry | None:
    """Edit an entry — marks old versions as not current and appends a new one."""
    entry = await get_entry(db, entry_id)
    if entry is None:
        return None

    if data.title is not None:
        entry.title = data.title

    # Mark all existing versions as not current
    for v in entry.versions:
        v.is_current = False

    next_version = max((v.version_number for v in entry.versions), default=0) + 1
    new_version = JournalEntryVersion(
        entry_id=entry.id,
        content=data.content,
        version_number=next_version,
        is_current=True,
    )
    db.add(new_version)

    # Reset processing flag since content changed
    entry.is_processed = False
    entry.processed_at = None

    await db.flush()
    await db.refresh(entry)
    return await get_entry(db, entry.id)  # type: ignore[return-value]


async def delete_entry(db: AsyncSession, entry_id: uuid.UUID) -> bool:
    """Delete a journal entry and all its versions."""
    entry = await get_entry(db, entry_id)
    if entry is None:
        return False
    await db.delete(entry)
    await db.flush()
    return True


def entry_to_response(entry: JournalEntry) -> JournalEntryResponse:
    """Convert a JournalEntry model to its API response schema."""
    current_content = None
    for v in entry.versions:
        if v.is_current:
            current_content = v.content
            break
    return JournalEntryResponse(
        id=entry.id,
        title=entry.title,
        is_processed=entry.is_processed,
        processed_at=entry.processed_at,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        current_content=current_content,
    )
