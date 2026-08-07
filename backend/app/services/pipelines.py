"""Service helpers for the manual-pipeline-trigger router.

Thin wrappers over ``ProcessingLog`` queries so the router can stay out
of the ORM layer (see architecture tests).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import uuid_utils
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import PipelineStatus, PipelineType
from backend.app.models.settings import ProcessingLog

# A process killed mid-pipeline leaves its ``ProcessingLog`` row stuck at
# status="started" forever — nothing ever comes back to mark it failed. Without
# a cutoff, one crash would permanently wedge the "already running?" check and
# the pipeline could never be triggered again. Anything older than this is
# treated as abandoned. The slowest observed pipeline (project generation, which
# retries a Go build) runs in minutes, so an hour is generous head-room.
STALE_RUN_AFTER = timedelta(hours=1)


def new_run_id() -> uuid.UUID:
    """Mint a fresh pipeline run id as a UUIDv7.

    UUIDv7 is time-ordered (first 48 bits are a Unix-ms timestamp), which
    gives much better B-tree index locality than UUIDv4 when rows are
    inserted roughly in chronological order — exactly the access pattern
    of ``processing_logs``. The return type remains the stdlib
    ``uuid.UUID`` so SQLAlchemy and Pydantic serialisation are unchanged;
    ``uuid_utils`` is only used as the generator.

    Centralised here so that swapping the algorithm again (e.g. to a
    prefixed string id) only touches one call site.
    """
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


async def get_active_run(
    db: AsyncSession,
    pipeline: PipelineType,
    *,
    now: datetime | None = None,
) -> ProcessingLog | None:
    """Return the in-flight run of *pipeline*, or ``None`` when it is idle.

    "In flight" means a ``status=started`` row that has not yet aged past
    :data:`STALE_RUN_AFTER`. Callers use this to refuse a duplicate manual
    trigger — these pipelines are expensive LLM calls, and running two at once
    burns tokens to produce two competing sessions.

    Args:
        db: Async session.
        pipeline: The pipeline to check.
        now: Override for the staleness reference point (tests).
    """
    cutoff = (now or datetime.now(UTC)) - STALE_RUN_AFTER
    stmt = (
        select(ProcessingLog)
        .where(
            ProcessingLog.pipeline == pipeline,
            ProcessingLog.status == PipelineStatus.STARTED,
            ProcessingLog.started_at >= cutoff,
        )
        .order_by(ProcessingLog.started_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def list_recent_runs(
    db: AsyncSession,
    *,
    limit: int = 20,
    pipeline: PipelineType | None = None,
) -> list[ProcessingLog]:
    """Return the most recent processing-log rows, newest first."""
    stmt = select(ProcessingLog).order_by(ProcessingLog.started_at.desc()).limit(limit)
    if pipeline is not None:
        stmt = (
            select(ProcessingLog)
            .where(ProcessingLog.pipeline == pipeline)
            .order_by(ProcessingLog.started_at.desc())
            .limit(limit)
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())
