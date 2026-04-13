"""Weekly project generation and evaluation pipeline.

Generates self-contained Go micro-projects and evaluates submissions.
Projects are written to workspace/projects/<date>/.

Run via cron weekly or manually via CLI.
"""

import logging
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.base import (
    PipelineStatus,
    PipelineType,
    ProjectStatus,
    ProjectTaskType,
    TriageSeverity,
    TriageSource,
)
from backend.app.models.project import ProjectEvaluation, ProjectTask, WeeklyProject
from backend.app.models.settings import ProcessingLog
from backend.app.models.triage import TriageItem
from backend.app.prompts import project_evaluation, project_generation
from backend.app.services import feedback as feedback_svc
from backend.app.services import onboarding as onboarding_svc
from backend.app.services import profile as profile_svc
from backend.app.services import project as project_svc
from backend.app.services.llm.client import llm_client
from backend.app.services.llm.models import ProjectEvaluationResult, ProjectGenerationResult

logger = logging.getLogger(__name__)


async def generate_project(db: AsyncSession) -> WeeklyProject:
    """Generate a new weekly Go project.

    Steps:
    1. Determine difficulty level from previous project evaluations
    2. Build context (profile, go experience, feedforward, previous themes)
    3. Call LLM to generate project
    4. Write files to workspace/projects/<date>/
    5. Store project record with tasks
    """
    log = ProcessingLog(
        pipeline=PipelineType.PROJECT_GENERATION,
        status=PipelineStatus.STARTED,
    )
    db.add(log)
    await db.flush()

    try:
        # Determine difficulty level
        difficulty = await _determine_difficulty(db)

        # Build context
        profile = await profile_svc.get_knowledge_profile(db)
        profile_summary = profile.model_dump_json(indent=2)

        # Go experience from onboarding
        onboarding = await onboarding_svc.get_onboarding_state(db)
        go_experience = "Not specified"
        if onboarding and onboarding.go_experience_level:
            go_experience = onboarding.go_experience_level

        # Feedforward
        all_feedback = await feedback_svc.list_all_feedback(db, limit=50)
        feedforward = [f.note for f in all_feedback if f.note]
        feedforward_text = "\n".join(f"- {n}" for n in feedforward[:10]) or "None"

        # Previous themes
        prev_projects = await project_svc.list_projects(db, limit=5)
        previous_themes = "\n".join(f"- {p.title}" for p in prev_projects) or "None (first project)"

        # Generate via LLM
        prompt = project_generation.USER_PROMPT_TEMPLATE.format(
            difficulty_level=difficulty,
            go_experience=go_experience,
            profile_summary=profile_summary,
            feedforward_signals=feedforward_text,
            previous_themes=previous_themes,
        )

        raw_result = await llm_client.chat_completion_json(
            pipeline="project_generation",
            messages=[
                {"role": "system", "content": project_generation.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=8192,
        )

        gen_result = ProjectGenerationResult.model_validate(raw_result)

        # Write files to disk
        project_date = date.today().isoformat()
        project_dir = Path(settings.workspace_projects_dir) / project_date
        project_dir.mkdir(parents=True, exist_ok=True)

        for f in gen_result.files:
            file_path = project_dir / f.path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f.content)

        # Write README
        readme_path = project_dir / "README.md"
        readme_path.write_text(gen_result.readme_content)

        # Store project record
        project = WeeklyProject(
            title=gen_result.title,
            description=gen_result.description,
            difficulty_level=difficulty,
            project_path=str(project_dir),
            status=ProjectStatus.ISSUED,
            metadata_={
                "files": [f.path for f in gen_result.files],
                "generated_difficulty": gen_result.difficulty_level,
            },
        )
        db.add(project)
        await db.flush()

        # Store tasks
        for i, t in enumerate(gen_result.tasks):
            try:
                task_type = ProjectTaskType(t.task_type)
            except ValueError:
                task_type = ProjectTaskType.FEATURE

            task = ProjectTask(
                project_id=project.id,
                title=t.title,
                description=t.description,
                task_type=task_type,
                order_index=i,
            )
            db.add(task)

        await db.flush()

        log.status = PipelineStatus.COMPLETED
        log.completed_at = datetime.now(UTC)
        log.metadata_ = {
            "project_id": str(project.id),
            "difficulty": difficulty,
            "files": len(gen_result.files),
            "tasks": len(gen_result.tasks),
        }
        await db.flush()

        logger.info("Project generated: %s (difficulty=%d)", project.title, difficulty)
        return project

    except Exception as e:
        log.status = PipelineStatus.FAILED
        log.error = str(e)
        log.completed_at = datetime.now(UTC)
        await db.flush()
        raise


async def evaluate_project(db: AsyncSession, project_id) -> dict:
    """Evaluate a submitted project.

    Steps:
    1. Load project with tasks
    2. Read original and submitted code from disk
    3. Call LLM for evaluation
    4. Store evaluation results
    5. Create triage items if needed
    """
    log = ProcessingLog(
        pipeline=PipelineType.PROJECT_EVALUATION,
        status=PipelineStatus.STARTED,
    )
    db.add(log)
    await db.flush()

    try:
        project = await project_svc.get_project(db, project_id)
        if project is None:
            raise ValueError(f"Project {project_id} not found")

        # Read code from disk
        project_dir = Path(project.project_path)
        submitted_code = _read_project_files(project_dir)

        tasks_text = "\n\n".join(
            f"### Task {i + 1}: {t.title}\nType: {t.task_type.value}\nDescription: {t.description}"
            for i, t in enumerate(project.tasks)
        )

        prompt = project_evaluation.USER_PROMPT_TEMPLATE.format(
            project_description=project.description,
            tasks=tasks_text,
            original_code="(See project metadata for original file listing)",
            submitted_code=submitted_code,
        )

        raw_result = await llm_client.chat_completion_json(
            pipeline="project_evaluation",
            messages=[
                {"role": "system", "content": project_evaluation.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        eval_result = ProjectEvaluationResult.model_validate(raw_result)

        # Store evaluation
        evaluation = ProjectEvaluation(
            project_id=project.id,
            code_quality_score=eval_result.code_quality_score,
            task_completion={
                te.task_title: {
                    "completed": te.completed,
                    "score": te.score,
                    "notes": te.quality_notes,
                }
                for te in eval_result.task_evaluations
            },
            test_results={"summary": eval_result.test_results_summary},
            overall_assessment=eval_result.overall_assessment,
            confidence=eval_result.confidence,
            raw_llm_output=eval_result.model_dump(),
        )
        db.add(evaluation)

        # Update project status
        project.status = ProjectStatus.EVALUATED

        # Create triage items
        for ti in eval_result.triage_items:
            triage = TriageItem(
                source=TriageSource.PROJECT_EVALUATION,
                source_id=project.id,
                title=ti.get("title", "Project evaluation issue"),
                description=ti.get("description", ""),
                context=ti,
                severity=TriageSeverity(ti.get("severity", "low")),
            )
            db.add(triage)

        await db.flush()

        log.status = PipelineStatus.COMPLETED
        log.completed_at = datetime.now(UTC)
        log.metadata_ = {
            "project_id": str(project_id),
            "code_quality": eval_result.code_quality_score,
            "difficulty_adjustment": eval_result.difficulty_adjustment,
        }
        await db.flush()

        return {
            "status": "completed",
            "code_quality": eval_result.code_quality_score,
            "difficulty_adjustment": eval_result.difficulty_adjustment,
        }

    except Exception as e:
        log.status = PipelineStatus.FAILED
        log.error = str(e)
        log.completed_at = datetime.now(UTC)
        await db.flush()
        raise


async def _determine_difficulty(db: AsyncSession) -> int:
    """Determine the difficulty level for the next project."""
    # Start at level 3 (conservative) and adjust based on previous evaluations
    base_difficulty = 3

    prev_projects = await project_svc.list_projects(db, limit=3)
    if not prev_projects:
        # Check onboarding for Go experience
        onboarding = await onboarding_svc.get_onboarding_state(db)
        if onboarding and onboarding.go_experience_level:
            level_map = {"none": 1, "beginner": 2, "intermediate": 4, "advanced": 6}
            return level_map.get(onboarding.go_experience_level, base_difficulty)
        return base_difficulty

    # Look at the most recent evaluated project
    for p in prev_projects:
        if p.status == ProjectStatus.EVALUATED and p.evaluation:
            # Use the evaluation's difficulty adjustment suggestion
            last_difficulty = p.difficulty_level
            # We'd use the adjustment from the evaluation — for now, increment if quality was good
            return min(10, max(1, last_difficulty))

    # Default: use last project's difficulty
    return prev_projects[0].difficulty_level if prev_projects else base_difficulty


def _read_project_files(project_dir: Path) -> str:
    """Read all Go files from a project directory into a single string."""
    if not project_dir.exists():
        return "(project directory not found)"

    files_content = []
    for go_file in sorted(project_dir.rglob("*.go")):
        relative = go_file.relative_to(project_dir)
        content = go_file.read_text()
        files_content.append(f"### {relative}\n```go\n{content}\n```")

    return "\n\n".join(files_content) or "(no Go files found)"
