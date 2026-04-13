"""Project service — weekly project lifecycle management."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.base import ProjectStatus
from backend.app.models.project import WeeklyProject
from backend.app.schemas.project import ProjectSubmitRequest


async def get_project(db: AsyncSession, project_id: uuid.UUID) -> WeeklyProject | None:
    """Get a weekly project with tasks and evaluation."""
    stmt = (
        select(WeeklyProject)
        .options(
            selectinload(WeeklyProject.tasks),
            selectinload(WeeklyProject.evaluation),
        )
        .where(WeeklyProject.id == project_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_current_project(db: AsyncSession) -> WeeklyProject | None:
    """Get the most recently issued project."""
    stmt = (
        select(WeeklyProject)
        .options(
            selectinload(WeeklyProject.tasks),
            selectinload(WeeklyProject.evaluation),
        )
        .order_by(WeeklyProject.issued_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_projects(
    db: AsyncSession, *, offset: int = 0, limit: int = 20
) -> list[WeeklyProject]:
    """List weekly projects (most recent first)."""
    stmt = (
        select(WeeklyProject).order_by(WeeklyProject.issued_at.desc()).offset(offset).limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def submit_project(
    db: AsyncSession, project_id: uuid.UUID, data: ProjectSubmitRequest
) -> WeeklyProject | None:
    """Mark a project as submitted for evaluation."""
    project = await get_project(db, project_id)
    if project is None:
        return None
    if project.status not in (ProjectStatus.ISSUED, ProjectStatus.IN_PROGRESS):
        return None  # can only submit active projects

    project.status = ProjectStatus.SUBMITTED
    project.submitted_at = datetime.now(UTC)
    if data.notes:
        meta = project.metadata_ or {}
        meta["submission_notes"] = data.notes
        project.metadata_ = meta

    await db.flush()
    await db.refresh(project)
    return project
