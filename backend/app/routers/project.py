"""Weekly project API — view, submit, and track projects."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.schemas.project import (
    ProjectSubmitRequest,
    WeeklyProjectDetailResponse,
    WeeklyProjectResponse,
)
from backend.app.services import project as project_svc

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get(
    "",
    response_model=list[WeeklyProjectResponse],
    summary="List weekly projects",
    response_description="Paginated list of weekly Go projects, most recent first",
)
async def list_projects(
    offset: int = Query(0, ge=0, description="Number of projects to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum projects to return"),
    db: AsyncSession = Depends(get_db),
) -> list[WeeklyProjectResponse]:
    """Return weekly projects ordered by issue date (most recent first).

    Each project is a self-contained Go codebase with source files, tests,
    and a set of tasks (bugs, features, refactors, optimizations).
    """
    projects = await project_svc.list_projects(db, offset=offset, limit=limit)
    return [WeeklyProjectResponse.model_validate(p) for p in projects]


@router.get(
    "/current",
    response_model=WeeklyProjectDetailResponse | None,
    summary="Get current project",
    response_description="The most recently issued project with tasks and evaluation, or null",
)
async def get_current_project(
    db: AsyncSession = Depends(get_db),
) -> WeeklyProjectDetailResponse | None:
    """Get the most recently issued weekly project.

    Returns `null` when no project has been issued yet.  Includes the full
    task list, project metadata, and evaluation (if submitted).
    """
    project = await project_svc.get_current_project(db)
    if project is None:
        return None
    return WeeklyProjectDetailResponse.model_validate(project)


@router.get(
    "/{project_id}",
    response_model=WeeklyProjectDetailResponse,
    summary="Get project details",
    response_description="Project with tasks, metadata, and evaluation",
    responses={404: {"description": "Project not found"}},
)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> WeeklyProjectDetailResponse:
    """Retrieve a specific weekly project with its tasks and evaluation."""
    project = await project_svc.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return WeeklyProjectDetailResponse.model_validate(project)


@router.post(
    "/{project_id}/submit",
    response_model=WeeklyProjectResponse,
    summary="Submit project for evaluation",
    response_description="The project with updated status",
    responses={
        404: {"description": "Project not found or not in a submittable state"},
    },
)
async def submit_project(
    project_id: uuid.UUID,
    data: ProjectSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> WeeklyProjectResponse:
    """Submit a completed project for AI evaluation.

    The project evaluation pipeline will assess code quality, task completion,
    and test results.  The evaluation must complete before the next weekly
    project is issued.
    """
    project = await project_svc.submit_project(db, project_id, data)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found or not submittable")
    return WeeklyProjectResponse.model_validate(project)
