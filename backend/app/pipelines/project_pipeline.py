"""Weekly project generation and evaluation pipeline.

Generates self-contained Go micro-projects and evaluates submissions.
Projects are written to workspace/projects/<date>/.

Run via cron weekly or manually via CLI.
"""

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.base import (
    FeedbackTargetType,
    PipelineStatus,
    PipelineType,
    ProjectStatus,
    ProjectTaskType,
    TriageSeverity,
    TriageSource,
)
from backend.app.models.project import (
    ProjectEvaluation,
    ProjectTask,
    WeeklyProject,
)
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


async def _load_project_title_lookup(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    stmt = select(WeeklyProject.id, WeeklyProject.title).where(WeeklyProject.id.in_(ids))
    result = await db.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


async def _load_project_detail_lookup(
    db: AsyncSession, ids: set[uuid.UUID]
) -> dict[uuid.UUID, WeeklyProject]:
    """Return full ``{id: WeeklyProject}`` for directional-steering use.

    Unlike ``_load_project_title_lookup`` we need description + difficulty
    here so the prompt can surface meaningful flavour, not just a title.
    """
    if not ids:
        return {}
    stmt = select(WeeklyProject).where(WeeklyProject.id.in_(ids))
    result = await db.execute(stmt)
    return {p.id: p for p in result.scalars().all()}


async def _load_task_lookup(
    db: AsyncSession, ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, uuid.UUID]]:
    if not ids:
        return {}
    stmt = select(ProjectTask.id, ProjectTask.title, ProjectTask.project_id).where(
        ProjectTask.id.in_(ids)
    )
    result = await db.execute(stmt)
    return {row[0]: (row[1], row[2]) for row in result.all()}


async def _load_task_detail_lookup(
    db: AsyncSession, ids: set[uuid.UUID]
) -> dict[uuid.UUID, ProjectTask]:
    """Return full ``{id: ProjectTask}`` for directional-steering use."""
    if not ids:
        return {}
    stmt = select(ProjectTask).where(ProjectTask.id.in_(ids))
    result = await db.execute(stmt)
    return {t.id: t for t in result.scalars().all()}


def _truncate(text: str, n: int = 140) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def _format_project_feedforward(
    feedback_items,
    project_titles: dict[uuid.UUID, str],
    task_info: dict[uuid.UUID, tuple[str, uuid.UUID]],
    max_items: int = 10,
) -> str:
    lines: list[str] = []
    for fb in feedback_items:
        if not fb.note:
            continue
        descriptor: str | None = None
        if fb.target_type == FeedbackTargetType.PROJECT:
            title = project_titles.get(fb.target_id)
            descriptor = f'project "{title}"' if title else "project (removed)"
        elif fb.target_type == FeedbackTargetType.PROJECT_TASK:
            info = task_info.get(fb.target_id)
            if info is not None:
                task_title, project_id = info
                parent = project_titles.get(project_id, "?")
                descriptor = f'task "{task_title}" in project "{parent}"'
            else:
                descriptor = "task (removed)"
        if descriptor is not None:
            reaction = f", {fb.reaction.value}" if fb.reaction else ""
            lines.append(f"- ({descriptor}{reaction}) {fb.note}")
        else:
            lines.append(f"- {fb.note}")
        if len(lines) >= max_items:
            break
    return "\n".join(lines) or "None"


def _format_liked_project_directions(
    liked_projects: list[WeeklyProject], max_items: int = 5
) -> str:
    """Summarise thumbs-up'd projects as *directional* signals.

    We surface title + difficulty + a short description so the LLM can lean
    toward the same flavour of project without re-issuing the literal one
    (titles are added to the hard avoid list separately).
    """
    if not liked_projects:
        return "None"
    sorted_likes = sorted(liked_projects, key=lambda p: p.created_at or datetime.min, reverse=True)
    lines: list[str] = []
    for p in sorted_likes[:max_items]:
        lines.append(f'- "{p.title}" (L{p.difficulty_level}): {_truncate(p.description, 120)}')
    return "\n".join(lines)


def _format_liked_task_flavours(
    liked_tasks: list[ProjectTask],
    project_titles: dict[uuid.UUID, str],
    max_items: int = 8,
) -> str:
    """Summarise thumbs-up'd tasks as *directional* signals for the task mix."""
    if not liked_tasks:
        return "None"
    sorted_likes = sorted(liked_tasks, key=lambda t: t.created_at or datetime.min, reverse=True)
    lines: list[str] = []
    for t in sorted_likes[:max_items]:
        t_type = t.task_type.value if t.task_type else "?"
        parent = project_titles.get(t.project_id, "?")
        lines.append(f'- [{t_type}] "{t.title}" (from "{parent}")')
    return "\n".join(lines)


def _format_avoid_titles(titles: set[str]) -> str:
    if not titles:
        return "None"
    return "\n".join(f"- {t}" for t in sorted(titles))


def _format_previous_themes(
    prev_projects: list[WeeklyProject],
    liked_ids: set[uuid.UUID],
    disliked_ids: set[uuid.UUID],
) -> str:
    """Previous project titles with reaction markers so the LLM knows which
    past directions were loved / hated vs. merely seen."""
    if not prev_projects:
        return "None (first project)"
    lines: list[str] = []
    for p in prev_projects:
        if p.id in liked_ids:
            marker = " (liked — lean toward this flavour, different title)"
        elif p.id in disliked_ids:
            marker = " (disliked — avoid this direction)"
        else:
            marker = ""
        lines.append(f"- {p.title}{marker}")
    return "\n".join(lines)


async def _verify_go_build(project_dir: Path) -> str | None:
    """Run ``go build ./...`` in *project_dir*.

    Ensures a ``go.mod`` exists first (auto-inits one if absent so the
    compiler has a valid module root).  Returns the combined stdout+stderr
    error string if the build fails, or ``None`` if it succeeds.
    """
    go = settings.go_executable

    # Auto-init a module if the LLM forgot to include go.mod.
    mod_file = project_dir / "go.mod"
    if not mod_file.exists():
        logger.debug("go.mod missing — running 'go mod init project' in %s", project_dir)
        init_proc = await asyncio.create_subprocess_exec(
            go,
            "mod",
            "init",
            "project",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, init_stderr = await init_proc.communicate()
        if init_proc.returncode != 0:
            return f"go mod init failed:\n{init_stderr.decode(errors='replace')}"

    proc = await asyncio.create_subprocess_exec(
        go,
        "build",
        "./...",
        cwd=str(project_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    except TimeoutError:
        proc.kill()
        return "go build timed out after 60 seconds"

    if proc.returncode != 0:
        combined = (stdout + stderr).decode(errors="replace").strip()
        return combined or f"go build exited with code {proc.returncode}"

    return None


def _write_gen_files(project_dir: Path, gen_result: "ProjectGenerationResult") -> None:
    """Write all generated source files and README to *project_dir*."""
    for f in gen_result.files:
        file_path = project_dir / f.path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(f.content)
    (project_dir / "README.md").write_text(gen_result.readme_content)


async def generate_project(
    db: AsyncSession,
    *,
    run_id: uuid.UUID | None = None,
) -> WeeklyProject:
    """Generate a new weekly Go project.

    Args:
        db: Async session.
        run_id: Optional pre-generated id for the ``ProcessingLog`` row.

    Steps:
    1. Determine difficulty level from previous project evaluations
    2. Build context (profile, go experience, feedforward, previous themes)
    3. Call LLM to generate project
    4. Write files to workspace/projects/<date>/
    5. Store project record with tasks
    """
    log_kwargs: dict = {
        "pipeline": PipelineType.PROJECT_GENERATION,
        "status": PipelineStatus.STARTED,
    }
    if run_id is not None:
        log_kwargs["id"] = run_id
    log = ProcessingLog(**log_kwargs)
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

        # Feedforward — scoped to projects + project_tasks, with item
        # descriptors so the LLM knows what each note refers to.
        relevant_feedback = await feedback_svc.list_feedback_by_target_types(
            db,
            [FeedbackTargetType.PROJECT, FeedbackTargetType.PROJECT_TASK],
            limit=50,
        )
        other_feedback = await feedback_svc.list_all_feedback(db, limit=50)
        seen_ids = {f.id for f in relevant_feedback}
        for fb in other_feedback:
            if fb.id not in seen_ids and fb.note:
                relevant_feedback.append(fb)
        proj_ids = {
            fb.target_id for fb in relevant_feedback if fb.target_type == FeedbackTargetType.PROJECT
        }
        task_ids = {
            fb.target_id
            for fb in relevant_feedback
            if fb.target_type == FeedbackTargetType.PROJECT_TASK
        }
        task_info = await _load_task_lookup(db, task_ids)
        # Tasks bring in their parent project IDs too
        proj_ids.update({p for _, p in task_info.values()})
        project_titles = await _load_project_title_lookup(db, proj_ids)
        feedforward_text = _format_project_feedforward(relevant_feedback, project_titles, task_info)

        # ── Reacted-to projects: thumbs-up (positive steering) and
        # thumbs-down (hard avoid). Both flavours also contribute TITLES to
        # a hard avoid list — re-issuing a literal past title is a waste
        # whether the user loved or hated it.
        liked_project_ids = await feedback_svc.list_liked_target_ids(db, FeedbackTargetType.PROJECT)
        disliked_project_ids = await feedback_svc.list_disliked_target_ids(
            db, FeedbackTargetType.PROJECT
        )
        reacted_project_ids = liked_project_ids | disliked_project_ids
        reacted_project_lookup = await _load_project_detail_lookup(db, reacted_project_ids)
        liked_projects = [
            p for pid, p in reacted_project_lookup.items() if pid in liked_project_ids
        ]
        avoid_project_titles = {p.title.strip() for p in reacted_project_lookup.values() if p.title}

        # Reacted-to tasks: same treatment. Titles go onto the per-task
        # avoid list; liked tasks additionally steer the task MIX.
        liked_task_ids = await feedback_svc.list_liked_target_ids(
            db, FeedbackTargetType.PROJECT_TASK
        )
        disliked_task_ids = await feedback_svc.list_disliked_target_ids(
            db, FeedbackTargetType.PROJECT_TASK
        )
        reacted_task_ids = liked_task_ids | disliked_task_ids
        reacted_task_lookup = await _load_task_detail_lookup(db, reacted_task_ids)
        liked_tasks = [t for tid, t in reacted_task_lookup.items() if tid in liked_task_ids]
        avoid_task_titles_set = {
            t.title.strip().lower() for t in reacted_task_lookup.values() if t.title
        }
        # Parent-title lookup for liked-task flavour rendering.
        liked_task_parent_ids = {t.project_id for t in liked_tasks}
        liked_task_parent_titles = await _load_project_title_lookup(db, liked_task_parent_ids)

        # Previous themes — annotated so the LLM can distinguish loved /
        # hated / merely-seen past directions.
        prev_projects = await project_svc.list_projects(db, limit=5)
        previous_themes = _format_previous_themes(
            prev_projects, liked_project_ids, disliked_project_ids
        )
        liked_project_directions_text = _format_liked_project_directions(liked_projects)
        liked_task_flavours_text = _format_liked_task_flavours(
            liked_tasks, liked_task_parent_titles
        )
        avoid_task_titles_text = _format_avoid_titles(
            {t.title.strip() for t in reacted_task_lookup.values() if t.title}
        )

        # Generate via LLM
        prompt = project_generation.USER_PROMPT_TEMPLATE.format(
            difficulty_level=difficulty,
            go_experience=go_experience,
            profile_summary=profile_summary,
            feedforward_signals=feedforward_text,
            previous_themes=previous_themes,
            liked_project_directions=liked_project_directions_text,
            liked_task_flavours=liked_task_flavours_text,
            avoid_task_titles=avoid_task_titles_text,
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

        _write_gen_files(project_dir, gen_result)

        # ── Compile check — one LLM retry on failure ─────────────────────
        compile_error = await _verify_go_build(project_dir)
        compile_retry_attempted = False
        compile_check_passed = compile_error is None

        if compile_error:
            logger.warning(
                "Generated project does not compile — retrying with error context.\n%s",
                compile_error,
            )
            compile_retry_attempted = True
            messages = [
                {"role": "system", "content": project_generation.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
                {
                    "role": "assistant",
                    "content": raw_result if isinstance(raw_result, str) else str(raw_result),
                },
                {
                    "role": "user",
                    "content": (
                        "The files you generated do not compile. Here are the errors from "
                        "`go build ./...`:\n\n"
                        f"```\n{compile_error}\n```\n\n"
                        "Please fix ALL compilation errors and return the complete corrected "
                        "JSON object with all files included. Do not omit any files."
                    ),
                },
            ]
            raw_result = await llm_client.chat_completion_json(
                pipeline="project_generation",
                messages=messages,
                max_tokens=8192,
            )
            gen_result = ProjectGenerationResult.model_validate(raw_result)
            _write_gen_files(project_dir, gen_result)

            retry_error = await _verify_go_build(project_dir)
            if retry_error:
                logger.error(
                    "Project still does not compile after retry — issuing anyway.\n%s",
                    retry_error,
                )
                compile_check_passed = False
            else:
                compile_check_passed = True
                logger.info("Project compiles cleanly after retry.")

        # ── Title-collision check on the generated project ──────────────
        # A single project is issued per run, so we can't drop-and-continue
        # the way the readings pipeline does for a batch. If the LLM ignored
        # the avoid list and chose a title we've already reacted to, log it
        # so it's visible in the run metadata but proceed — dropping would
        # leave the user with no weekly project.
        gen_title = (gen_result.title or "").strip()
        project_title_collision = gen_title in avoid_project_titles

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

        # Store tasks, applying hard-avoid + diversity gates as a
        # belt-and-braces enforcement on top of the prompt instructions.
        skipped_avoid_tasks = 0
        skipped_duplicate_tasks = 0
        seen_task_titles: set[str] = set()
        stored_task_count = 0

        for t in gen_result.tasks:
            title_key = (t.title or "").strip().lower()

            # Hard filter: never re-issue a task the user has already
            # reacted to. Thumbs-down → they rejected it; thumbs-up → they
            # already did it, so it has no learning value this week.
            if title_key and title_key in avoid_task_titles_set:
                logger.info("Skipping previously-reacted task: %s", t.title)
                skipped_avoid_tasks += 1
                continue

            # Diversity guard: refuse duplicate task titles within this
            # project. Projects should have a DISTINCT set of tasks.
            if title_key and title_key in seen_task_titles:
                logger.info("Skipping duplicate task title within project: %s", t.title)
                skipped_duplicate_tasks += 1
                continue

            try:
                task_type = ProjectTaskType(t.task_type)
            except ValueError:
                task_type = ProjectTaskType.FEATURE

            task = ProjectTask(
                project_id=project.id,
                title=t.title,
                description=t.description,
                task_type=task_type,
                order_index=stored_task_count,
            )
            db.add(task)
            stored_task_count += 1
            if title_key:
                seen_task_titles.add(title_key)

        await db.flush()

        log.status = PipelineStatus.COMPLETED
        log.completed_at = datetime.now(UTC)
        log.metadata_ = {
            "project_id": str(project.id),
            "difficulty": difficulty,
            "files": len(gen_result.files),
            "tasks_generated": len(gen_result.tasks),
            "tasks_stored": stored_task_count,
            "skipped_avoid_tasks": skipped_avoid_tasks,
            "skipped_duplicate_tasks": skipped_duplicate_tasks,
            "project_title_collision": project_title_collision,
            "compile_check_passed": compile_check_passed,
            "compile_retry_attempted": compile_retry_attempted,
            # Kept for backwards-compat with anything reading the old key.
            "tasks": stored_task_count,
        }
        await db.flush()

        if project_title_collision:
            logger.warning(
                "Generated project title collides with a previously-reacted title: %r",
                gen_title,
            )

        logger.info(
            "Project generated: %s (difficulty=%d, tasks stored=%d of %d)",
            project.title,
            difficulty,
            stored_task_count,
            len(gen_result.tasks),
        )
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
