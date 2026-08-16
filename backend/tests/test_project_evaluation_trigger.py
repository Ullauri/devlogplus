"""Tests for triggering project evaluation.

`evaluate_project` was fully implemented but unreachable: no router endpoint,
no cron, no CLI — its only caller in the repo was a BDD test. A submitted
project therefore sat in `submitted` forever, behind a button labelled "Submit
for Evaluation".

The wiring these tests hold in place is small and easy to get subtly wrong:
`_run_in_background` calls its pipeline as `fn(session, run_id=run_id)`, so a
pipeline that does not accept `run_id` raises TypeError on the first real
invocation — in a background task, where nobody is watching.
"""

import inspect
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import database
from backend.app.config import settings
from backend.app.models.base import PipelineType, ProjectStatus
from backend.app.models.project import WeeklyProject
from backend.app.models.settings import ProcessingLog
from backend.app.pipelines.project_pipeline import evaluate_project

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_project(db: AsyncSession, *, status: ProjectStatus) -> WeeklyProject:
    project = WeeklyProject(
        title="Connection Pool Health Monitor",
        description="A CLI tool that simulates a connection pool",
        difficulty_level=5,
        project_path="workspace/projects/test-project",
        status=status,
    )
    db.add(project)
    await db.flush()
    await db.commit()
    await db.refresh(project)
    return project


async def test_evaluate_project_accepts_run_id() -> None:
    """The signature `_run_in_background` requires.

    It invokes `fn(session, run_id=run_id)` unconditionally. Without a
    keyword-only `run_id`, every trigger fails with TypeError inside a
    background task, which surfaces as a run that silently never happens.
    """
    params = inspect.signature(evaluate_project).parameters

    assert "run_id" in params
    assert params["run_id"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["run_id"].default is None


async def test_trigger_returns_202_with_the_run_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    project = await _create_project(db_session, status=ProjectStatus.SUBMITTED)

    response = await client.post(f"/api/v1/pipelines/project-evaluation/run/{project.id}")

    assert response.status_code == 202
    body = response.json()
    assert body["pipeline"] == "project_evaluation"
    # The caller polls GET /pipelines/runs for this id, so it must be usable.
    uuid.UUID(body["run_id"])


async def test_trigger_accepts_an_unknown_project_id(client: AsyncClient) -> None:
    """Queueing is deliberately not a lookup.

    The endpoint returns 202 before touching the database, mirroring
    quiz-evaluation. A missing project fails inside the pipeline and is
    recorded there as a failed run, which is where run failures belong.
    """
    response = await client.post(f"/api/v1/pipelines/project-evaluation/run/{uuid.uuid4()}")

    assert response.status_code == 202


async def test_trigger_rejects_a_malformed_project_id(client: AsyncClient) -> None:
    response = await client.post("/api/v1/pipelines/project-evaluation/run/not-a-uuid")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# The background half writes to the test database, not the developer's own
# ---------------------------------------------------------------------------
async def test_the_background_session_is_not_the_configured_database() -> None:
    """The leak that made these tests visible in production data.

    `_run_in_background` opens its own session because the request has already
    returned. Overriding `get_db` does not touch that session, so for as long
    as the factory was captured at import time it resolved to `DATABASE_URL` —
    the developer's real database. Every run of this file logged two failed
    `project_evaluation` rows there, naming project ids that only ever existed
    in a torn-down container.
    """
    bound_url = str(database.async_session_factory.kw["bind"].url)

    assert "devlogplus_test" in bound_url
    assert bound_url != settings.database_url


async def test_a_failed_run_is_logged_to_the_test_database(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """And the failure is still recorded — in the container, where it belongs.

    Asserting the row lands here is what proves the previous test is measuring
    the session the pipeline actually used, rather than one nothing reads.
    """
    missing_id = uuid.uuid4()

    response = await client.post(f"/api/v1/pipelines/project-evaluation/run/{missing_id}")
    assert response.status_code == 202

    logs = (
        (
            await db_session.execute(
                select(ProcessingLog).where(
                    ProcessingLog.pipeline == PipelineType.PROJECT_EVALUATION
                )
            )
        )
        .scalars()
        .all()
    )

    assert [log.error for log in logs] == [f"Project {missing_id} not found"]
