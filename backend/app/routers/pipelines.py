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
import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
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
    fn: Callable[..., Awaitable[object]],
    label: str,
    run_id: uuid.UUID,
) -> None:
    """Invoke *fn* with a fresh AsyncSession, committing on success.

    The pre-generated ``run_id`` is forwarded so the pipeline's
    ``ProcessingLog`` row carries the same id that was already returned to
    the HTTP client.
    """
    logger.info("Starting manual pipeline run: %s (run_id=%s)", label, run_id)
    async with async_session_factory() as session:
        try:
            await fn(session, run_id=run_id)
            await session.commit()
            logger.info("Manual pipeline run finished: %s (run_id=%s)", label, run_id)
        except Exception:
            # The pipeline itself writes its own ProcessingLog entry with
            # status=failed and error=..., so the UI can surface it.
            await session.rollback()
            logger.exception("Manual pipeline run failed: %s (run_id=%s)", label, run_id)


# ---------------------------------------------------------------------------
# Trigger endpoints
# ---------------------------------------------------------------------------
def _accepted(pipeline: ManualPipelineName, human: str, run_id: uuid.UUID) -> PipelineRunAccepted:
    return PipelineRunAccepted(
        pipeline=pipeline,
        run_id=run_id,
        message=f"{human} pipeline queued. Check run history for progress.",
    )


# Documented on every guarded trigger so the generated OpenAPI spec (and the
# TS types built from it) carry the conflict case.
_CONFLICT_RESPONSE = {
    status.HTTP_409_CONFLICT: {"description": "This pipeline is already running"},
}


async def _reject_if_running(db: AsyncSession, pipeline: PipelineType, human: str) -> None:
    """Refuse a manual trigger while the same pipeline is already in flight.

    These runs are minutes-long LLM calls. Firing a second one concurrently
    doubles the token spend and races two pipelines to write competing
    sessions, so a duplicate trigger is always a mistake rather than a
    legitimate request.
    """
    active = await pipelines_svc.get_active_run(db, pipeline)
    if active is None:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"{human} is already running (started "
            f"{active.started_at.isoformat()}). Wait for it to finish, or check "
            f"run history if it looks stuck."
        ),
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
        "observe progress.\n\n"
        "Returns 409 if a profile-update run is already in flight."
    ),
    responses=_CONFLICT_RESPONSE,
)
async def run_profile_update(
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunAccepted:
    await _reject_if_running(db, PipelineType.PROFILE_UPDATE, "Profile update")
    run_id = pipelines_svc.new_run_id()
    bg.add_task(
        _run_in_background,
        profile_update_pipeline.run_profile_update,
        "profile_update",
        run_id,
    )
    return _accepted("profile_update", "Profile update", run_id)


@router.post(
    "/quiz/run",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger the quiz-generation pipeline",
    description=(
        "Generates a new weekly quiz session immediately rather than waiting "
        "for the Monday 3:00 AM cron. Runs in the background; poll "
        "`GET /pipelines/runs` for progress.\n\n"
        "Returns 409 if a quiz-generation run is already in flight."
    ),
    responses=_CONFLICT_RESPONSE,
)
async def run_quiz_generation(
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunAccepted:
    await _reject_if_running(db, PipelineType.QUIZ_GENERATION, "Quiz generation")
    run_id = pipelines_svc.new_run_id()
    bg.add_task(
        _run_in_background,
        quiz_pipeline.generate_quiz,
        "quiz_generation",
        run_id,
    )
    return _accepted("quiz_generation", "Quiz generation", run_id)


@router.post(
    "/quiz-evaluation/run/{session_id}",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger quiz evaluation for a completed session",
    description=(
        "Re-runs the quiz evaluation pipeline for a specific completed quiz "
        "session. Use this when automatic evaluation failed or was never "
        "triggered. Runs in the background; poll `GET /pipelines/runs` for "
        "progress."
    ),
)
async def run_quiz_evaluation(
    session_id: uuid.UUID,
    bg: BackgroundTasks,
) -> PipelineRunAccepted:
    run_id = pipelines_svc.new_run_id()

    async def _evaluate(db: AsyncSession, *, run_id: uuid.UUID) -> None:
        await quiz_pipeline.evaluate_quiz(db, session_id, run_id=run_id)

    bg.add_task(
        _run_in_background,
        _evaluate,
        "quiz_evaluation",
        run_id,
    )
    return _accepted("quiz_evaluation", "Quiz evaluation", run_id)


@router.post(
    "/readings/run",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger the reading-generation pipeline",
    description=(
        "Generates a new weekly batch of reading recommendations immediately "
        "rather than waiting for the Monday 3:30 AM cron. Runs in the "
        "background; poll `GET /pipelines/runs` for progress.\n\n"
        "Returns 409 if a reading-generation run is already in flight."
    ),
    responses=_CONFLICT_RESPONSE,
)
async def run_reading_generation(
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunAccepted:
    await _reject_if_running(db, PipelineType.READING_GENERATION, "Reading generation")
    run_id = pipelines_svc.new_run_id()
    bg.add_task(
        _run_in_background,
        reading_pipeline.generate_readings,
        "reading_generation",
        run_id,
    )
    return _accepted("reading_generation", "Reading generation", run_id)


@router.post(
    "/project/run",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger the project-generation pipeline",
    description=(
        "Generates a new weekly Go micro-project immediately rather than "
        "waiting for the Monday 4:00 AM cron. Runs in the background; poll "
        "`GET /pipelines/runs` for progress. Note: generates files under "
        "`workspace/projects/<date>/`.\n\n"
        "Returns 409 if a project-generation run is already in flight."
    ),
    responses=_CONFLICT_RESPONSE,
)
async def run_project_generation(
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunAccepted:
    await _reject_if_running(db, PipelineType.PROJECT_GENERATION, "Project generation")
    run_id = pipelines_svc.new_run_id()
    bg.add_task(
        _run_in_background,
        project_pipeline.generate_project,
        "project_generation",
        run_id,
    )
    return _accepted("project_generation", "Project generation", run_id)


@router.post(
    "/project-evaluation/run/{project_id}",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger evaluation for a submitted project",
    description=(
        "Evaluates a submitted project: reads the files back off disk, scores "
        "them against the project's task list, and files triage items for any "
        "problems found. Submitting a project queues this automatically — use "
        "this endpoint to re-run when that evaluation failed. Runs in the "
        "background; poll `GET /pipelines/runs` for progress."
    ),
)
async def run_project_evaluation(
    project_id: uuid.UUID,
    bg: BackgroundTasks,
) -> PipelineRunAccepted:
    run_id = pipelines_svc.new_run_id()

    async def _evaluate(db: AsyncSession, *, run_id: uuid.UUID) -> None:
        await project_pipeline.evaluate_project(db, project_id, run_id=run_id)

    bg.add_task(
        _run_in_background,
        _evaluate,
        "project_evaluation",
        run_id,
    )
    return _accepted("project_evaluation", "Project evaluation", run_id)


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
