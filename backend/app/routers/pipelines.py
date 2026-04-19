"""Manual pipeline triggers.

Expose an opt-in escape hatch for users who don't want to wait for the
scheduled cron invocations. Each endpoint queues the corresponding
pipeline to run in the background (after the HTTP response is returned)
and records its progress in the ``processing_logs`` table, which is
available via :py:func:`list_runs`.

Note on layering: this is the one place routers legitimately depend on
the ``pipelines`` package. See ``tests/test_architecture.py`` for the
documented exception.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import async_session_factory, get_db
from backend.app.models.base import PipelineType
from backend.app.pipelines import (
    profile_update as profile_update_pipeline,
)
from backend.app.pipelines import (
    project_pipeline,
    quiz_pipeline,
    reading_pipeline,
)
from backend.app.schemas.pipelines import (
    ManualPipelineName,
    PipelineRunAccepted,
    PipelineRunInfo,
)
from backend.app.services import pipelines as pipelines_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


# ---------------------------------------------------------------------------
# Background runner — opens its own session so the HTTP request can return
# immediately while the pipeline runs for potentially minutes.
# ---------------------------------------------------------------------------
async def _run_in_background(
    fn: Callable[[AsyncSession], Awaitable[object]],
    label: str,
) -> None:
    """Invoke *fn* with a fresh AsyncSession, committing on success."""
    logger.info("Starting manual pipeline run: %s", label)
    async with async_session_factory() as session:
        try:
            await fn(session)
            await session.commit()
            logger.info("Manual pipeline run finished: %s", label)
        except Exception:
            # The pipeline itself writes its own ProcessingLog entry with
            # status=failed and error=..., so the UI can surface it.
            await session.rollback()
            logger.exception("Manual pipeline run failed: %s", label)


# ---------------------------------------------------------------------------
# Trigger endpoints
# ---------------------------------------------------------------------------
def _accepted(pipeline: ManualPipelineName, human: str) -> PipelineRunAccepted:
    return PipelineRunAccepted(
        pipeline=pipeline,
        message=f"{human} pipeline queued. Check run history for progress.",
    )


@router.post(
    "/profile-update/run",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger the profile-update pipeline",
    description=(
        "Runs the nightly profile-update pipeline on demand. Normally this "
        "runs automatically at 2:00 AM via cron; use this endpoint when you "
        "don't want to wait.\n\n"
        "The pipeline runs in the background — the response returns "
        "immediately with status=queued. Poll `GET /pipelines/runs` to "
        "observe progress."
    ),
)
async def run_profile_update(bg: BackgroundTasks) -> PipelineRunAccepted:
    bg.add_task(
        _run_in_background, profile_update_pipeline.run_profile_update, "profile_update"
    )
    return _accepted("profile_update", "Profile update")


@router.post(
    "/quiz/run",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger the quiz-generation pipeline",
    description=(
        "Generates a new weekly quiz session immediately rather than waiting "
        "for the Monday 3:00 AM cron. Runs in the background; poll "
        "`GET /pipelines/runs` for progress."
    ),
)
async def run_quiz_generation(bg: BackgroundTasks) -> PipelineRunAccepted:
    bg.add_task(_run_in_background, quiz_pipeline.generate_quiz, "quiz_generation")
    return _accepted("quiz_generation", "Quiz generation")


@router.post(
    "/readings/run",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger the reading-generation pipeline",
    description=(
        "Generates a new weekly batch of reading recommendations immediately "
        "rather than waiting for the Monday 3:30 AM cron. Runs in the "
        "background; poll `GET /pipelines/runs` for progress."
    ),
)
async def run_reading_generation(bg: BackgroundTasks) -> PipelineRunAccepted:
    bg.add_task(
        _run_in_background, reading_pipeline.generate_readings, "reading_generation"
    )
    return _accepted("reading_generation", "Reading generation")


@router.post(
    "/project/run",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger the project-generation pipeline",
    description=(
        "Generates a new weekly Go micro-project immediately rather than "
        "waiting for the Monday 4:00 AM cron. Runs in the background; poll "
        "`GET /pipelines/runs` for progress. Note: generates files under "
        "`workspace/projects/<date>/`."
    ),
)
async def run_project_generation(bg: BackgroundTasks) -> PipelineRunAccepted:
    bg.add_task(
        _run_in_background, project_pipeline.generate_project, "project_generation"
    )
    return _accepted("project_generation", "Project generation")


# ---------------------------------------------------------------------------
# Run history — used by the Settings page to display progress.
# ---------------------------------------------------------------------------
@router.get(
    "/runs",
    response_model=list[PipelineRunInfo],
    summary="List recent pipeline runs",
    description=(
        "Returns the most recent entries from the processing log, newest "
        "first. Useful for displaying the status of manually-triggered or "
        "scheduled pipeline runs in the UI."
    ),
)
async def list_runs(
    limit: int = Query(
        20,
        ge=1,
        le=200,
        description="Maximum number of runs to return (newest first).",
    ),
    pipeline: PipelineType | None = Query(
        None,
        description="Optional filter — return only runs of a given pipeline.",
    ),
    db: AsyncSession = Depends(get_db),
) -> list[PipelineRunInfo]:
    logs = await pipelines_svc.list_recent_runs(db, limit=limit, pipeline=pipeline)
    return [PipelineRunInfo.model_validate(log) for log in logs]
