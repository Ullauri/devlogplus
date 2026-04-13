"""Reading service — recommendations and allowlist management."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.reading import ReadingAllowlist, ReadingRecommendation
from backend.app.schemas.reading import AllowlistEntryCreate, AllowlistEntryUpdate


# ---------------------------------------------------------------------------
# Reading recommendations
# ---------------------------------------------------------------------------
async def list_recommendations(
    db: AsyncSession,
    *,
    batch_date: date | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[ReadingRecommendation]:
    """List reading recommendations, optionally filtered by batch date."""
    stmt = select(ReadingRecommendation).order_by(
        ReadingRecommendation.batch_date.desc(),
        ReadingRecommendation.created_at.desc(),
    )
    if batch_date is not None:
        stmt = stmt.where(ReadingRecommendation.batch_date == batch_date)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_latest_batch_date(db: AsyncSession) -> date | None:
    """Return the most recent batch date."""
    stmt = (
        select(ReadingRecommendation.batch_date)
        .order_by(ReadingRecommendation.batch_date.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------
async def list_allowlist(db: AsyncSession) -> list[ReadingAllowlist]:
    """Return all allowlist entries."""
    stmt = select(ReadingAllowlist).order_by(ReadingAllowlist.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def add_allowlist_entry(db: AsyncSession, data: AllowlistEntryCreate) -> ReadingAllowlist:
    """Add a new domain to the allowlist."""
    entry = ReadingAllowlist(
        domain=data.domain,
        name=data.name,
        description=data.description,
        is_default=False,
    )
    db.add(entry)
    await db.flush()
    return entry


async def update_allowlist_entry(
    db: AsyncSession, entry_id: uuid.UUID, data: AllowlistEntryUpdate
) -> ReadingAllowlist | None:
    """Update an allowlist entry."""
    stmt = select(ReadingAllowlist).where(ReadingAllowlist.id == entry_id)
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    if data.name is not None:
        entry.name = data.name
    if data.description is not None:
        entry.description = data.description
    await db.flush()
    return entry


async def delete_allowlist_entry(db: AsyncSession, entry_id: uuid.UUID) -> bool:
    """Remove a domain from the allowlist."""
    stmt = select(ReadingAllowlist).where(ReadingAllowlist.id == entry_id)
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        return False
    await db.delete(entry)
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# Default allowlist seeding
# ---------------------------------------------------------------------------
DEFAULT_ALLOWLIST = [
    ("go.dev", "Go Official", "Go language documentation and blog"),
    ("go.dev/blog", "Go Blog", "Official Go blog"),
    ("docs.python.org", "Python Docs", "Official Python documentation"),
    ("developer.mozilla.org", "MDN", "Mozilla Developer Network"),
    ("docs.aws.amazon.com", "AWS Docs", "Amazon Web Services documentation"),
    ("postgresql.org/docs", "PostgreSQL Docs", "Official PostgreSQL documentation"),
    ("learn.microsoft.com", "Microsoft Learn", "Microsoft technical documentation"),
    ("martinfowler.com", "Martin Fowler", "Software architecture and design"),
    ("thoughtworks.com", "Thoughtworks", "Technology radar and engineering insights"),
    ("pkg.go.dev", "Go Packages", "Go package documentation"),
    ("kubernetes.io/docs", "Kubernetes Docs", "Official Kubernetes documentation"),
    ("redis.io/docs", "Redis Docs", "Official Redis documentation"),
    ("docker.com/blog", "Docker Blog", "Docker engineering blog"),
    ("engineering.fb.com", "Meta Engineering", "Meta engineering blog"),
    ("netflixtechblog.com", "Netflix Tech Blog", "Netflix engineering blog"),
    ("blog.golang.org", "Go Blog (legacy)", "Legacy Go blog URL"),
]


async def seed_default_allowlist(db: AsyncSession) -> int:
    """Insert default allowlist entries if they don't already exist. Returns count added."""
    existing = await list_allowlist(db)
    existing_domains = {e.domain for e in existing}
    count = 0
    for domain, name, description in DEFAULT_ALLOWLIST:
        if domain not in existing_domains:
            entry = ReadingAllowlist(
                domain=domain, name=name, description=description, is_default=True
            )
            db.add(entry)
            count += 1
    if count:
        await db.flush()
    return count
