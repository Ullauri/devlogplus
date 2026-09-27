"""Pipeline triggers.

Nothing in DevLog+ runs on a schedule, so these endpoints are the only
way a pipeline runs at all. Each one queues the corresponding pipeline
to run in the background (after the HTTP response is returned) and
records its progress in the ``processing_logs`` table, which is
available via :py:func:`list_runs`.

Note on layering: this is the one place routers legitimately depend on
the ``pipelines`` package. See ``tests/test_architecture.py`` for the
documented exception.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db, session_scope
from backend.app.models.base import PipelineStatus, PipelineType
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
    PipelineRunsDismissed,
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

    The ``run_id`` already returned to the HTTP client is forwarded so the
    pipeline records its outcome on that ``ProcessingLog`` row — adopting
    the row the trigger reserved, or creating it under that id for the
    evaluation triggers, which reserve nothing.
    """
    logger.info("Starting manual pipeline run: %s (run_id=%s)", label, run_id)
    pipeline = PipelineType(label)
    # Pipelines catch their own errors and record status=failed, so an
    # exception reaching here means that record never committed: the session
    # rolls back as it closes, taking the outcome with it. The cleanup runs
    # after the session has closed, so a dead connection that fails the
    # rollback cannot skip it.
    try:
        async with session_scope() as session:
            await fn(session, run_id=run_id)
            await session.commit()
    except asyncio.CancelledError:
        await _cancelled(pipeline, run_id)
        raise
    except Exception as exc:
        task = asyncio.current_task()
        if task is not None and task.cancelling():
            # Cancelled mid-query, and closing the session then raised over
            # the CancelledError. Whoever cancelled us must still see it.
            await _cancelled(pipeline, run_id)
            raise asyncio.CancelledError from exc
        logger.exception("Manual pipeline run failed: %s (run_id=%s)", label, run_id)
        await _fail_abandoned_run(
            pipeline, run_id, f"Run ended without recording an outcome: {exc!r}"
        )
    else:
        logger.info("Manual pipeline run finished: %s (run_id=%s)", label, run_id)


# Cleanup tasks outlive a second cancellation of the run that started them;
# the event loop holds tasks only weakly, so something here has to hold them.
_pending_cleanups: set[asyncio.Task[None]] = set()


async def _cancelled(pipeline: PipelineType, run_id: uuid.UUID) -> None:
    """Fail a run a worker reload or shutdown cancelled mid-flight.

    Shielded, so a second cancellation of this run does not interrupt the
    cleanup while the loop keeps running. It cannot survive the loop itself
    being torn down: then the row stays ``started`` until
    :data:`~backend.app.services.pipelines.STALE_RUN_AFTER`, as after a crash.
    """
    logger.warning("Manual pipeline run cancelled: %s (run_id=%s)", pipeline, run_id)
    cleanup = asyncio.ensure_future(
        _fail_abandoned_run(pipeline, run_id, "Run was cancelled before recording an outcome")
    )
    _pending_cleanups.add(cleanup)
    cleanup.add_done_callback(_pending_cleanups.discard)
    await asyncio.shield(cleanup)


async def _fail_abandoned_run(pipeline: PipelineType, run_id: uuid.UUID, error: str) -> None:
    """Record a failure the pipeline could not, so its reserved row stops blocking.

    Otherwise the row the trigger reserved stays ``started``, and the
    trigger's guard refuses every new run until it goes stale. Runs nobody
    reserved have no committed row to mark, and are left as they were.
    """
    try:
        async with session_scope() as session:
            if await pipelines_svc.fail_abandoned_run(session, run_id, pipeline, error):
                await session.commit()
    except Exception:
        logger.exception("Could not mark abandoned run %s failed", run_id)


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


async def _reserve_run(db: AsyncSession, pipeline: PipelineType, human: str) -> uuid.UUID:
    """Reserve a manual run of *pipeline* and return its id, or refuse with 409.

    These runs are minutes-long LLM calls. Firing a second one concurrently
    doubles the token spend and races two pipelines to write competing
    sessions, so a duplicate trigger is always a mistake rather than a
    legitimate request.
    """
    try:
        run = await pipelines_svc.reserve_run(db, pipeline)
    except pipelines_svc.PipelineAlreadyRunningError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{human} is already running (started "
                f"{exc.active.started_at.isoformat()}). Wait for it to finish, or "
                f"check run history if it looks stuck."
            ),
        ) from exc
    # Commit here, not in get_db's teardown. The background run adopts this
    # row from its own session, and a concurrent trigger is waiting on the
    # reservation's lock; both need the row committed before this returns.
    await db.commit()
    return run.id


@router.post(
    "/profile-update/run",
    response_model=PipelineRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger the profile-update pipeline",
    description=(
        "Processes new journal entries and refreshes the Knowledge Profile. "
        "Nothing runs this on a schedule, so call it whenever you want the "
        "profile brought up to date.\n\n"
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
    run_id = await _reserve_run(db, PipelineType.PROFILE_UPDATE, "Profile update")
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
    summary="Trigger the quiz-generation pipeline",
    description=(
        "Generates a new quiz session from the current Knowledge Profile. "
        "Runs in the background; poll "
        "`GET /pipelines/runs` for progress.\n\n"
        "Returns 409 if a quiz-generation run is already in flight."
    ),
    responses=_CONFLICT_RESPONSE,
)
async def run_quiz_generation(
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunAccepted:
    run_id = await _reserve_run(db, PipelineType.QUIZ_GENERATION, "Quiz generation")
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
    summary="Trigger the reading-generation pipeline",
    description=(
        "Generates a new batch of reading recommendations. Runs in the "
        "background; poll `GET /pipelines/runs` for progress.\n\n"
        "Returns 409 if a reading-generation run is already in flight."
    ),
    responses=_CONFLICT_RESPONSE,
)
async def run_reading_generation(
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunAccepted:
    run_id = await _reserve_run(db, PipelineType.READING_GENERATION, "Reading generation")
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
    summary="Trigger the project-generation pipeline",
    description=(
        "Generates a new Go micro-project. Runs in the background; poll "
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
    run_id = await _reserve_run(db, PipelineType.PROJECT_GENERATION, "Project generation")
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
        "first. Useful for displaying the status of pipeline runs in the UI."
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
    run_status: PipelineStatus | None = Query(
        None,
        alias="status",
        description="Optional filter — return only runs in a given state.",
    ),
    include_dismissed: bool = Query(
        True,
        description=(
            "Whether to include runs the user has dismissed. Defaults to "
            "true, so run history shows everything; the Triage attention "
            "list passes false."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> list[PipelineRunInfo]:
    logs = await pipelines_svc.list_recent_runs(
        db,
        limit=limit,
        pipeline=pipeline,
        run_status=run_status,
        include_dismissed=include_dismissed,
    )
    return [PipelineRunInfo.model_validate(log) for log in logs]


# ---------------------------------------------------------------------------
# Dismissal — acknowledging a run so it leaves the Triage attention list.
# Nothing here changes a run's status or deletes it; the processing log stays
# a complete record of what ran.
# ---------------------------------------------------------------------------
@router.post(
    "/runs/dismiss-failed",
    response_model=PipelineRunsDismissed,
    summary="Dismiss every failed pipeline run",
    description=(
        "Marks all currently-failed runs as acknowledged in one call, so a "
        "backlog of failures can be cleared without dismissing each one. "
        "Runs that are still in flight or that completed successfully are "
        "left alone. Returns the number newly dismissed — already-dismissed "
        "runs are not counted again."
    ),
)
async def dismiss_failed_runs(
    db: AsyncSession = Depends(get_db),
) -> PipelineRunsDismissed:
    count = await pipelines_svc.dismiss_failed_runs(db)
    return PipelineRunsDismissed(dismissed=count)


@router.post(
    "/runs/{run_id}/dismiss",
    response_model=PipelineRunInfo,
    summary="Dismiss a pipeline run",
    description=(
        "Marks one run as acknowledged. The run stays in the processing log "
        "and in the run history — dismissal only removes it from the list of "
        "things needing attention. Idempotent: dismissing a run twice keeps "
        "the first timestamp."
    ),
    responses={status.HTTP_404_NOT_FOUND: {"description": "No such pipeline run"}},
)
async def dismiss_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunInfo:
    run = await pipelines_svc.dismiss_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline run not found",
        )
    return PipelineRunInfo.model_validate(run)
