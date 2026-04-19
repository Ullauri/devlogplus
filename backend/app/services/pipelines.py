"""Service helpers for the manual-pipeline-trigger router.

Thin wrappers over ``ProcessingLog`` queries so the router can stay out
of the ORM layer (see architecture tests).
"""

from __future__ import annotations

import uuid

import uuid_utils
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import PipelineType
from backend.app.models.settings import ProcessingLog


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
