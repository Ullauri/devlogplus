"""Reading service — recommendations and allowlist management."""

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from backend.app.models.reading import ReadingAllowlist, ReadingRecommendation
from backend.app.schemas.reading import (
    AllowlistEntryCreate,
    AllowlistEntryUpdate,
    ReadingRecommendationUpdate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URL reachability validation
# ---------------------------------------------------------------------------
# The LLM occasionally hallucinates plausible-but-nonexistent article URLs
# (e.g. made-up martinfowler.com slugs). Before surfacing a recommendation
# to the user we confirm the page actually resolves with a cheap HEAD request
# (falling back to GET for servers that reject HEAD).
#
# Kept here — rather than in the pipeline layer — because it is a reusable
# piece of "reading" domain logic and is easier to unit-test in isolation.

# Browser-ish UA: some sites (notably martinfowler.com CDN) return 403 for
# bare httpx/<ver> user agents.
_URL_VALIDATION_UA = "Mozilla/5.0 (compatible; DevLogPlus-LinkCheck/1.0; +https://github.com/)"


async def _check_single_url(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float,  # noqa: ASYNC109 — passed to httpx, not asyncio.timeout
) -> tuple[str, bool, str | None]:
    """Return ``(url, is_reachable, reason)``.

    A URL is considered reachable if the server responds with any status in
    the range 200–399 (after following redirects). A 405 Method Not Allowed
    on HEAD triggers a GET fallback, since some origins refuse HEAD.
    """
    headers = {"User-Agent": _URL_VALIDATION_UA}
    try:
        resp = await client.head(url, follow_redirects=True, timeout=timeout, headers=headers)
        # Some servers block HEAD — retry once with GET.
        if resp.status_code in (403, 405, 501):
            resp = await client.get(url, follow_redirects=True, timeout=timeout, headers=headers)
        if 200 <= resp.status_code < 400:
            return url, True, None
        return url, False, f"HTTP {resp.status_code}"
    except httpx.TimeoutException:
        return url, False, "timeout"
    except httpx.HTTPError as exc:
        return url, False, f"{type(exc).__name__}: {exc}"


async def validate_urls(
    urls: list[str],
    *,
    timeout: float = 5.0,  # noqa: ASYNC109 — passed to httpx, not asyncio.timeout
    concurrency: int = 8,
) -> dict[str, tuple[bool, str | None]]:
    """Concurrently check a batch of URLs.

    Returns a mapping ``{url: (is_reachable, reason_if_unreachable)}``.
    Never raises — network failures translate to ``(False, reason)``.
    """
    if not urls:
        return {}

    sem = asyncio.Semaphore(concurrency)
    # Unique list while preserving order so repeats don't get checked twice.
    unique: list[str] = list(dict.fromkeys(urls))

    async with httpx.AsyncClient() as client:

        async def _bounded(u: str) -> tuple[str, bool, str | None]:
            async with sem:
                return await _check_single_url(client, u, timeout=timeout)

        results = await asyncio.gather(*(_bounded(u) for u in unique))

    return {u: (ok, reason) for (u, ok, reason) in results}


# ---------------------------------------------------------------------------
# Reading recommendations
# ---------------------------------------------------------------------------
async def list_recommendations(
    db: AsyncSession,
    *,
    batch_date: date | None = None,
    active_only: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> list[ReadingRecommendation]:
    """List reading recommendations, optionally filtered by batch date.

    When ``active_only`` is ``True`` the result is restricted to the "active
    list" — items the user might still care about: the latest batch plus any
    prior-batch items they explicitly saved, excluding anything dismissed.
    Dismissed items never appear in the active list regardless of batch.
    """
    stmt = select(ReadingRecommendation).order_by(
        ReadingRecommendation.batch_date.desc(),
        ReadingRecommendation.created_at.desc(),
    )
    if batch_date is not None:
        stmt = stmt.where(ReadingRecommendation.batch_date == batch_date)
    if active_only:
        latest = await get_latest_batch_date(db)
        stmt = stmt.where(ReadingRecommendation.dismissed_at.is_(None))
        if latest is not None:
            stmt = stmt.where(
                or_(
                    ReadingRecommendation.batch_date == latest,
                    ReadingRecommendation.saved_at.is_not(None),
                )
            )
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_recommendations(
    db: AsyncSession,
    *,
    batch_date: date | None = None,
    active_only: bool = False,
) -> int:
    """Return the total number of reading recommendations matching the filter."""
    stmt = select(count(ReadingRecommendation.id))
    if batch_date is not None:
        stmt = stmt.where(ReadingRecommendation.batch_date == batch_date)
    if active_only:
        latest = await get_latest_batch_date(db)
        stmt = stmt.where(ReadingRecommendation.dismissed_at.is_(None))
        if latest is not None:
            stmt = stmt.where(
                or_(
                    ReadingRecommendation.batch_date == latest,
                    ReadingRecommendation.saved_at.is_not(None),
                )
            )
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def get_latest_batch_date(db: AsyncSession) -> date | None:
    """Return the most recent batch date."""
    stmt = (
        select(ReadingRecommendation.batch_date)
        .order_by(ReadingRecommendation.batch_date.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_recommendation(
    db: AsyncSession, recommendation_id: uuid.UUID
) -> ReadingRecommendation | None:
    """Fetch a single recommendation by id."""
    stmt = select(ReadingRecommendation).where(ReadingRecommendation.id == recommendation_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_recommendation_state(
    db: AsyncSession,
    recommendation_id: uuid.UUID,
    data: ReadingRecommendationUpdate,
) -> ReadingRecommendation | None:
    """Apply a partial state update (read / saved / dismissed) to a recommendation.

    Semantics:

    * ``True`` stamps the corresponding ``*_at`` column with ``now()``,
      *preserving* any prior value (idempotent — re-marking read does not
      reset the timestamp).
    * ``False`` clears the column back to ``NULL``.
    * ``None`` leaves it untouched.

    Cross-field invariants (applied after explicit updates):

    * Dismissing an item clears ``saved_at`` — dismissed trumps saved.
    * Saving an item clears ``dismissed_at`` — un-dismisses.
    """
    rec = await get_recommendation(db, recommendation_id)
    if rec is None:
        return None

    now = datetime.now(UTC)

    if data.read is True and rec.read_at is None:
        rec.read_at = now
    elif data.read is False:
        rec.read_at = None

    if data.saved is True and rec.saved_at is None:
        rec.saved_at = now
    elif data.saved is False:
        rec.saved_at = None

    if data.dismissed is True and rec.dismissed_at is None:
        rec.dismissed_at = now
    elif data.dismissed is False:
        rec.dismissed_at = None

    # Invariants
    if data.dismissed is True:
        rec.saved_at = None
    if data.saved is True:
        rec.dismissed_at = None

    await db.flush()
    # ``updated_at`` is refreshed server-side via ``onupdate=func.now()``;
    # eagerly reload it so the response schema can access it without
    # triggering lazy IO during Pydantic serialization.
    await db.refresh(rec)
    return rec


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
    # Personal blogs from respected practitioners
    ("joelonsoftware.com", "Joel on Software", "Joel Spolsky on software engineering"),
    ("blog.codinghorror.com", "Coding Horror", "Jeff Atwood on programming"),
    ("danluu.com", "Dan Luu", "Deep dives on performance, hardware, and engineering culture"),
    ("lethain.com", "Irrational Exuberance", "Will Larson on engineering leadership"),
    ("overreacted.io", "Overreacted", "Dan Abramov on React and JavaScript"),
    (
        "blog.pragmaticengineer.com",
        "The Pragmatic Engineer",
        "Gergely Orosz on software engineering practice",
    ),
    ("allthingsdistributed.com", "All Things Distributed", "Werner Vogels on distributed systems"),
    # Company engineering blogs
    ("stackoverflow.blog", "Stack Overflow Blog", "Stack Overflow engineering and community"),
    ("github.blog", "GitHub Blog", "GitHub product and engineering updates"),
    ("stripe.com/blog", "Stripe Blog", "Stripe engineering and product"),
    ("shopify.engineering", "Shopify Engineering", "Shopify engineering blog"),
    ("slack.engineering", "Slack Engineering", "Slack engineering blog"),
    ("eng.uber.com", "Uber Engineering", "Uber engineering blog"),
    ("blog.cloudflare.com", "Cloudflare Blog", "Cloudflare engineering and security"),
    ("fly.io/blog", "Fly.io Blog", "Fly.io engineering and infrastructure"),
    ("jepsen.io", "Jepsen", "Distributed systems correctness analyses"),
    # Research and reference
    ("research.google", "Google Research", "Google Research publications and blog"),
    ("highscalability.com", "High Scalability", "Architecture case studies at scale"),
    ("rust-lang.org", "Rust Lang", "Official Rust language site"),
    ("doc.rust-lang.org", "Rust Docs", "Official Rust documentation"),
    ("typescriptlang.org/docs", "TypeScript Docs", "Official TypeScript documentation"),
    # Learning / tutorials
    ("geeksforgeeks.org", "GeeksforGeeks", "Tutorials, practice problems, and CS fundamentals"),
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
