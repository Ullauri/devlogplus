"""Tests for the weekly project API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import ProjectStatus, ProjectTaskType
from backend.app.models.project import ProjectTask, WeeklyProject

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_project(
    db: AsyncSession,
    *,
    title: str = "Test Project",
    status: ProjectStatus = ProjectStatus.ISSUED,
) -> WeeklyProject:
    """Helper to insert a project with a task."""
    project = WeeklyProject(
        title=title,
        description="A test Go micro-project",
        difficulty_level=2,
        project_path="workspace/projects/test-project",
        status=status,
    )
    db.add(project)
    await db.flush()

    task = ProjectTask(
        project_id=project.id,
        title="Fix the bug",
        description="There's a nil pointer dereference",
        task_type=ProjectTaskType.BUG_FIX,
        order_index=0,
    )
    db.add(task)
    await db.commit()
    await db.refresh(project)
    return project


async def test_list_projects_empty(client: AsyncClient):
    """Empty list when no projects exist."""
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_current_project_none(client: AsyncClient):
    """No current project when none exist."""
    resp = await client.get("/api/v1/projects/current")
    assert resp.status_code == 200
    assert resp.json() is None


async def test_list_projects(client: AsyncClient, db_session: AsyncSession):
    """List projects after creating one."""
    await _create_project(db_session, title="Listed Project")
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


async def test_get_current_project(client: AsyncClient, db_session: AsyncSession):
    """Get the most recently issued project."""
    await _create_project(db_session, title="Current Project")
    resp = await client.get("/api/v1/projects/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data is not None
    assert "tasks" in data


async def test_get_project_detail(client: AsyncClient, db_session: AsyncSession):
    """Get a project by ID with tasks."""
    project = await _create_project(db_session, title="Detail Project")
    resp = await client.get(f"/api/v1/projects/{project.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Detail Project"
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["task_type"] == "bug_fix"


async def test_get_project_not_found(client: AsyncClient):
    """Nonexistent project returns 404."""
    resp = await client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_submit_project(client: AsyncClient, db_session: AsyncSession):
    """Submit a project for evaluation."""
    project = await _create_project(db_session, title="Submittable")
    resp = await client.post(
        f"/api/v1/projects/{project.id}/submit",
        json={"notes": "Completed all tasks"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "submitted"
    assert data["submitted_at"] is not None


async def test_submit_project_not_found(client: AsyncClient):
    """Submitting a nonexistent project returns 404."""
    resp = await client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/submit",
        json={},
    )
    assert resp.status_code == 404


async def test_submit_already_submitted_project(client: AsyncClient, db_session: AsyncSession):
    """Cannot re-submit an already submitted project."""
    project = await _create_project(
        db_session, title="Already Done", status=ProjectStatus.SUBMITTED
    )
    resp = await client.post(
        f"/api/v1/projects/{project.id}/submit",
        json={},
    )
    # Service returns None for non-submittable, router returns 404
    assert resp.status_code == 404
