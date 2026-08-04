"""Tests for pipeline error handling behaviour.

Critical contract: pipelines must NOT re-raise exceptions after recording a
failed ProcessingLog entry. If they do, the background runner's rollback will
discard the status=failed write, leaving the log stuck at status=started.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import (
    PipelineStatus,
    PipelineType,
    ProjectStatus,
    QuizQuestionType,
    QuizSessionStatus,
)
from backend.app.models.journal import JournalEntry, JournalEntryVersion
from backend.app.models.project import ProjectEvaluation, WeeklyProject
from backend.app.models.quiz import QuizQuestion, QuizSession
from backend.app.models.settings import ProcessingLog
from backend.app.pipelines import profile_update as profile_update_pipeline
from backend.app.pipelines import quiz_pipeline
from backend.app.pipelines.project_pipeline import _determine_difficulty, _format_avoid_titles
from backend.app.prompts import project_generation
from backend.app.services import pipelines as pipelines_svc

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_unprocessed_entry(db: AsyncSession) -> JournalEntry:
    entry = JournalEntry(title="Test entry", is_processed=False)
    db.add(entry)
    await db.flush()

    version = JournalEntryVersion(
        entry_id=entry.id,
        content="Learned about Go channels today.",
        version_number=1,
        is_current=True,
    )
    db.add(version)
    await db.flush()
    return entry


async def test_pipeline_records_failed_status_on_llm_error(db_session: AsyncSession):
    """When an LLM call raises, the pipeline must not re-raise.

    The ProcessingLog row must end up with status=failed after the pipeline
    returns, so the background runner's commit preserves that status.
    """
    await _create_unprocessed_entry(db_session)

    with patch(
        "backend.app.pipelines.profile_update.llm_client.chat_completion_json",
        new=AsyncMock(side_effect=RuntimeError("simulated LLM failure")),
    ):
        # Pipeline must return normally — no exception should propagate
        await profile_update_pipeline.run_profile_update(db_session)

    await db_session.commit()

    log_stmt = select(ProcessingLog).order_by(ProcessingLog.started_at.desc()).limit(1)
    log_result = await db_session.execute(log_stmt)
    log = log_result.scalar_one()

    assert log.status == PipelineStatus.FAILED
    assert "simulated LLM failure" in (log.error or "")


# ---------------------------------------------------------------------------
# Bug 1: _determine_difficulty must apply difficulty_adjustment from evaluation
# ---------------------------------------------------------------------------


async def _create_evaluated_project(
    db: AsyncSession,
    *,
    difficulty_level: int = 5,
    difficulty_adjustment: int = 0,
) -> WeeklyProject:
    """Create a WeeklyProject with EVALUATED status and a ProjectEvaluation
    whose raw_llm_output contains the given difficulty_adjustment."""
    project = WeeklyProject(
        title="Test Evaluated Project",
        description="A test project",
        difficulty_level=difficulty_level,
        project_path="workspace/projects/test",
        status=ProjectStatus.EVALUATED,
    )
    db.add(project)
    await db.flush()

    evaluation = ProjectEvaluation(
        project_id=project.id,
        code_quality_score=7.5,
        task_completion={},
        overall_assessment="Good work",
        confidence=0.9,
        raw_llm_output={
            "difficulty_adjustment": difficulty_adjustment,
            "code_quality_score": 7.5,
            "overall_assessment": "Good work",
        },
    )
    db.add(evaluation)
    await db.flush()
    return project


async def test_determine_difficulty_applies_positive_adjustment(db_session: AsyncSession):
    """_determine_difficulty must add difficulty_adjustment=+1 to last_difficulty."""
    project = await _create_evaluated_project(
        db_session, difficulty_level=5, difficulty_adjustment=1
    )

    # list_projects will return this project; we also need evaluation to be loaded.
    # Patch list_projects to return a project with evaluation eagerly loaded.
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    stmt = (
        sa_select(WeeklyProject)
        .options(selectinload(WeeklyProject.evaluation))
        .where(WeeklyProject.id == project.id)
    )
    result = await db_session.execute(stmt)
    loaded_project = result.scalar_one()

    with (
        patch(
            "backend.app.pipelines.project_pipeline.project_svc.list_projects",
            new=AsyncMock(return_value=[loaded_project]),
        ),
        patch(
            "backend.app.pipelines.project_pipeline.onboarding_svc.get_onboarding_state",
            new=AsyncMock(return_value=None),
        ),
    ):
        difficulty = await _determine_difficulty(db_session)

    assert difficulty == 6  # 5 + 1


async def test_determine_difficulty_zero_adjustment_unchanged(db_session: AsyncSession):
    """_determine_difficulty must return last_difficulty unchanged when adjustment=0."""
    project = await _create_evaluated_project(
        db_session, difficulty_level=5, difficulty_adjustment=0
    )

    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    stmt = (
        sa_select(WeeklyProject)
        .options(selectinload(WeeklyProject.evaluation))
        .where(WeeklyProject.id == project.id)
    )
    result = await db_session.execute(stmt)
    loaded_project = result.scalar_one()

    with (
        patch(
            "backend.app.pipelines.project_pipeline.project_svc.list_projects",
            new=AsyncMock(return_value=[loaded_project]),
        ),
        patch(
            "backend.app.pipelines.project_pipeline.onboarding_svc.get_onboarding_state",
            new=AsyncMock(return_value=None),
        ),
    ):
        difficulty = await _determine_difficulty(db_session)

    assert difficulty == 5  # 5 + 0


async def test_determine_difficulty_missing_key_defaults_to_zero(db_session: AsyncSession):
    """_determine_difficulty defaults adjustment to 0 when key is absent from raw_llm_output."""
    project = WeeklyProject(
        title="No Adjustment Key",
        description="A project without difficulty_adjustment in raw output",
        difficulty_level=4,
        project_path="workspace/projects/test2",
        status=ProjectStatus.EVALUATED,
    )
    db_session.add(project)
    await db_session.flush()

    evaluation = ProjectEvaluation(
        project_id=project.id,
        code_quality_score=6.0,
        task_completion={},
        overall_assessment="OK",
        confidence=0.8,
        raw_llm_output={"code_quality_score": 6.0},  # no difficulty_adjustment key
    )
    db_session.add(evaluation)
    await db_session.flush()

    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    stmt = (
        sa_select(WeeklyProject)
        .options(selectinload(WeeklyProject.evaluation))
        .where(WeeklyProject.id == project.id)
    )
    result = await db_session.execute(stmt)
    loaded_project = result.scalar_one()

    with (
        patch(
            "backend.app.pipelines.project_pipeline.project_svc.list_projects",
            new=AsyncMock(return_value=[loaded_project]),
        ),
        patch(
            "backend.app.pipelines.project_pipeline.onboarding_svc.get_onboarding_state",
            new=AsyncMock(return_value=None),
        ),
    ):
        difficulty = await _determine_difficulty(db_session)

    assert difficulty == 4  # 4 + 0 (default)


# ---------------------------------------------------------------------------
# Bug 2: _format_avoid_titles works correctly; prompt template has placeholder
# (sync helpers — use a class to avoid inheriting the module asyncio mark)
# ---------------------------------------------------------------------------


class TestFormatAvoidTitles:
    async def test_non_empty(self):
        """_format_avoid_titles returns a string containing all given titles."""
        titles = {"My Project", "Another Project"}
        result = _format_avoid_titles(titles)
        assert result  # non-empty
        assert "My Project" in result
        assert "Another Project" in result

    async def test_empty_set(self):
        """_format_avoid_titles returns the empty/none signal text for an empty set."""
        result = _format_avoid_titles(set())
        assert result == "None"

    async def test_prompt_template_has_placeholder(self):
        """The USER_PROMPT_TEMPLATE must contain {avoid_project_titles} placeholder."""
        assert "{avoid_project_titles}" in project_generation.USER_PROMPT_TEMPLATE


# ---------------------------------------------------------------------------
# Bug 1 (Issue #5): evaluate_quiz must honour the run_id passed by the caller
# ---------------------------------------------------------------------------


async def _create_completed_quiz_session(
    db: AsyncSession, *, num_questions: int = 1
) -> QuizSession:
    """Create a COMPLETED quiz session so evaluate_quiz can process it."""
    session = QuizSession(status=QuizSessionStatus.COMPLETED, question_count=num_questions)
    db.add(session)
    await db.flush()

    for i in range(num_questions):
        q = QuizQuestion(
            session_id=session.id,
            question_text=f"What is concept {i + 1}?",
            question_type=QuizQuestionType.REINFORCEMENT,
            order_index=i,
        )
        db.add(q)

    await db.flush()
    return session


async def test_evaluate_quiz_uses_provided_run_id(db_session: AsyncSession):
    """evaluate_quiz must create a ProcessingLog whose id matches the caller-supplied run_id.

    Bug: before the fix, evaluate_quiz ignored any run_id parameter (it didn't
    accept one), so the log row got an auto-generated UUID — making it
    impossible for the HTTP client to correlate the 202 run_id with a log entry.
    """
    session = await _create_completed_quiz_session(db_session)
    await db_session.commit()

    predetermined_run_id = uuid.uuid4()

    # Minimal mock: return a valid-shaped LLM result so the pipeline completes.
    fake_eval_result = {
        "evaluations": [],
        "triage_items": [],
    }

    with patch(
        "backend.app.pipelines.quiz_pipeline.llm_client.chat_completion_json",
        new=AsyncMock(return_value=fake_eval_result),
    ):
        await quiz_pipeline.evaluate_quiz(db_session, session.id, run_id=predetermined_run_id)

    await db_session.commit()

    # Find the ProcessingLog row for this evaluation run.
    stmt = (
        select(ProcessingLog)
        .where(ProcessingLog.pipeline == PipelineType.QUIZ_EVALUATION)
        .order_by(ProcessingLog.started_at.desc())
        .limit(1)
    )
    result = await db_session.execute(stmt)
    log = result.scalar_one()

    assert (
        log.id == predetermined_run_id
    ), f"ProcessingLog.id {log.id} does not match the caller-supplied run_id {predetermined_run_id}"


# ---------------------------------------------------------------------------
# Suggestion: LLM client singleton must be closed during lifespan teardown
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Token budgets: the quiz calls emit one JSON object per question, so a fixed
# max_tokens truncates mid-array and loses the whole response.
# ---------------------------------------------------------------------------


class TestQuizTokenBudget:
    async def test_budget_scales_with_item_count(self):
        ten = quiz_pipeline._budgeted_max_tokens(2048, 1600, 10)
        twenty = quiz_pipeline._budgeted_max_tokens(2048, 1600, 20)
        assert twenty > ten

    async def test_budget_clears_the_observed_truncation_point(self):
        """A 10-question quiz must get well past the 4096 default that failed."""
        budget = quiz_pipeline._budgeted_max_tokens(
            quiz_pipeline._QUIZ_GENERATION_BASE_TOKENS,
            quiz_pipeline._QUIZ_GENERATION_TOKENS_PER_QUESTION,
            10,
        )
        assert budget > 4096 * 3

    async def test_budget_is_capped(self):
        """A large quiz_question_count must not ask for an absurd budget."""
        budget = quiz_pipeline._budgeted_max_tokens(2048, 1600, 500)
        assert budget == quiz_pipeline._QUIZ_MAX_TOKENS_CEILING

    async def test_zero_items_still_gets_a_budget(self):
        assert quiz_pipeline._budgeted_max_tokens(2048, 1600, 0) == 2048 + 1600


async def test_generate_quiz_requests_a_scaled_token_budget(db_session: AsyncSession):
    """generate_quiz must pass an explicit max_tokens, not fall back to 4096.

    Regression: the pipeline relied on ``chat_completion_json``'s 4096 default,
    which truncated 10-question responses at finish_reason=length.
    """
    mock_llm = AsyncMock(return_value={"questions": []})
    with patch(
        "backend.app.pipelines.quiz_pipeline.llm_client.chat_completion_json",
        new=mock_llm,
    ):
        await quiz_pipeline.generate_quiz(db_session)

    assert mock_llm.await_count == 1
    assert mock_llm.await_args.kwargs["max_tokens"] > 4096


async def test_evaluate_quiz_requests_a_scaled_token_budget(db_session: AsyncSession):
    """evaluate_quiz must budget per answer rather than using the 4096 default."""
    session = await _create_completed_quiz_session(db_session, num_questions=10)
    await db_session.commit()

    mock_llm = AsyncMock(return_value={"evaluations": [], "triage_items": []})
    with patch(
        "backend.app.pipelines.quiz_pipeline.llm_client.chat_completion_json",
        new=mock_llm,
    ):
        await quiz_pipeline.evaluate_quiz(db_session, session.id)

    assert mock_llm.await_count == 1
    assert mock_llm.await_args.kwargs["max_tokens"] > 4096


# ---------------------------------------------------------------------------
# Concurrency guard: a manual trigger must be refused while the same pipeline
# is already in flight — these are minutes-long LLM calls and a second run
# races the first to write a competing session.
# ---------------------------------------------------------------------------


async def _add_run(
    db: AsyncSession,
    pipeline: PipelineType,
    status: PipelineStatus,
    *,
    age: timedelta = timedelta(0),
) -> ProcessingLog:
    log = ProcessingLog(
        pipeline=pipeline,
        status=status,
        started_at=datetime.now(UTC) - age,
    )
    db.add(log)
    await db.flush()
    return log


class TestGetActiveRun:
    async def test_none_when_idle(self, db_session: AsyncSession):
        assert await pipelines_svc.get_active_run(db_session, PipelineType.QUIZ_GENERATION) is None

    async def test_finds_a_started_run(self, db_session: AsyncSession):
        await _add_run(db_session, PipelineType.QUIZ_GENERATION, PipelineStatus.STARTED)
        active = await pipelines_svc.get_active_run(db_session, PipelineType.QUIZ_GENERATION)
        assert active is not None

    async def test_ignores_finished_runs(self, db_session: AsyncSession):
        await _add_run(db_session, PipelineType.QUIZ_GENERATION, PipelineStatus.COMPLETED)
        await _add_run(db_session, PipelineType.QUIZ_GENERATION, PipelineStatus.FAILED)
        assert await pipelines_svc.get_active_run(db_session, PipelineType.QUIZ_GENERATION) is None

    async def test_ignores_other_pipelines(self, db_session: AsyncSession):
        await _add_run(db_session, PipelineType.READING_GENERATION, PipelineStatus.STARTED)
        assert await pipelines_svc.get_active_run(db_session, PipelineType.QUIZ_GENERATION) is None

    async def test_stale_started_run_does_not_block(self, db_session: AsyncSession):
        """A crashed process leaves status=started forever — it must not wedge
        the pipeline permanently."""
        await _add_run(
            db_session,
            PipelineType.QUIZ_GENERATION,
            PipelineStatus.STARTED,
            age=pipelines_svc.STALE_RUN_AFTER + timedelta(minutes=5),
        )
        assert await pipelines_svc.get_active_run(db_session, PipelineType.QUIZ_GENERATION) is None


async def test_quiz_trigger_returns_409_while_running(
    client: AsyncClient, db_session: AsyncSession
):
    await _add_run(db_session, PipelineType.QUIZ_GENERATION, PipelineStatus.STARTED)
    await db_session.commit()

    response = await client.post("/api/v1/pipelines/quiz/run")

    assert response.status_code == 409
    assert "already running" in response.json()["detail"]


async def test_quiz_trigger_accepted_when_idle(client: AsyncClient, db_session: AsyncSession):
    """The guard must not block a legitimate trigger — a finished run is not
    in flight."""
    await _add_run(db_session, PipelineType.QUIZ_GENERATION, PipelineStatus.COMPLETED)
    await db_session.commit()

    with patch(
        "backend.app.pipelines.quiz_pipeline.llm_client.chat_completion_json",
        new=AsyncMock(return_value={"questions": []}),
    ):
        response = await client.post("/api/v1/pipelines/quiz/run")

    assert response.status_code == 202


async def test_quiz_trigger_not_blocked_by_a_different_pipeline(
    client: AsyncClient, db_session: AsyncSession
):
    await _add_run(db_session, PipelineType.PROFILE_UPDATE, PipelineStatus.STARTED)
    await db_session.commit()

    with patch(
        "backend.app.pipelines.quiz_pipeline.llm_client.chat_completion_json",
        new=AsyncMock(return_value={"questions": []}),
    ):
        response = await client.post("/api/v1/pipelines/quiz/run")

    assert response.status_code == 202


@pytest.mark.parametrize(
    ("path", "pipeline"),
    [
        ("/api/v1/pipelines/profile-update/run", PipelineType.PROFILE_UPDATE),
        ("/api/v1/pipelines/quiz/run", PipelineType.QUIZ_GENERATION),
        ("/api/v1/pipelines/readings/run", PipelineType.READING_GENERATION),
        ("/api/v1/pipelines/project/run", PipelineType.PROJECT_GENERATION),
    ],
)
async def test_every_generation_trigger_is_guarded(
    client: AsyncClient,
    db_session: AsyncSession,
    path: str,
    pipeline: PipelineType,
):
    await _add_run(db_session, pipeline, PipelineStatus.STARTED)
    await db_session.commit()

    response = await client.post(path)

    assert response.status_code == 409


async def test_lifespan_closes_llm_client():
    """The FastAPI lifespan must call llm_client.close() on shutdown.

    Without this, the httpx.AsyncClient is never explicitly closed,
    which produces ResourceWarning on interpreter exit.
    """
    from unittest.mock import AsyncMock, patch

    from backend.app.main import app, lifespan

    mock_close = AsyncMock()
    with patch("backend.app.main.llm_client.close", mock_close):
        async with lifespan(app):
            pass  # simulates startup + shutdown

    mock_close.assert_called_once()
