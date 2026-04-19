"""Service helpers for the manual-pipeline-trigger router.

Thin wrappers over ``ProcessingLog`` queries so the router can stay out
of the ORM layer (see architecture tests).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import PipelineType
from backend.app.models.settings import ProcessingLog


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
