"""Service layer for full data export / import."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    Feedback,
    JournalEntry,
    JournalEntryVersion,
    OnboardingState,
    ProfileSnapshot,
    ProjectEvaluation,
    ProjectTask,
    QuizAnswer,
    QuizEvaluation,
    QuizQuestion,
    QuizSession,
    ReadingAllowlist,
    ReadingRecommendation,
    Topic,
    TopicRelationship,
    TriageItem,
    UserSettings,
    WeeklyProject,
)
from backend.app.schemas.transfer import (
    DataExportBundle,
    FeedbackExport,
    ImportResult,
    JournalEntryExport,
    JournalEntryVersionExport,
    OnboardingStateExport,
    ProfileSnapshotExport,
    ProjectEvaluationExport,
    ProjectTaskExport,
    QuizAnswerExport,
    QuizEvaluationExport,
    QuizQuestionExport,
    QuizSessionExport,
    ReadingAllowlistExport,
    ReadingRecommendationExport,
    TopicExport,
    TopicRelationshipExport,
    TriageItemExport,
    UserSettingsExport,
    WeeklyProjectExport,
)

logger = logging.getLogger(__name__)

APP_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
async def export_all(db: AsyncSession) -> DataExportBundle:
    """Read every user-data table and return a serialisable bundle."""

    async def _all(model):
        result = await db.execute(select(model))
        return result.scalars().all()

    journal_entries = await _all(JournalEntry)
    journal_entry_versions = await _all(JournalEntryVersion)
    topics = await _all(Topic)
    topic_relationships = await _all(TopicRelationship)
    profile_snapshots = await _all(ProfileSnapshot)
    quiz_sessions = await _all(QuizSession)
    quiz_questions = await _all(QuizQuestion)
    quiz_answers = await _all(QuizAnswer)
    quiz_evaluations = await _all(QuizEvaluation)
    reading_recommendations = await _all(ReadingRecommendation)
    reading_allowlist = await _all(ReadingAllowlist)
    weekly_projects = await _all(WeeklyProject)
    project_tasks = await _all(ProjectTask)
    project_evaluations = await _all(ProjectEvaluation)
    feedback = await _all(Feedback)
    triage_items = await _all(TriageItem)
    user_settings = await _all(UserSettings)
    onboarding_state = await _all(OnboardingState)

    bundle = DataExportBundle(
        format_version=1,
        exported_at=datetime.now(UTC),
        app_version=APP_VERSION,
        journal_entries=[JournalEntryExport.model_validate(r) for r in journal_entries],
        journal_entry_versions=[
            JournalEntryVersionExport.model_validate(r) for r in journal_entry_versions
        ],
        topics=[TopicExport.model_validate(r) for r in topics],
        topic_relationships=[
            TopicRelationshipExport.model_validate(r) for r in topic_relationships
        ],
        profile_snapshots=[ProfileSnapshotExport.model_validate(r) for r in profile_snapshots],
        quiz_sessions=[QuizSessionExport.model_validate(r) for r in quiz_sessions],
        quiz_questions=[QuizQuestionExport.model_validate(r) for r in quiz_questions],
        quiz_answers=[QuizAnswerExport.model_validate(r) for r in quiz_answers],
        quiz_evaluations=[QuizEvaluationExport.model_validate(r) for r in quiz_evaluations],
        reading_recommendations=[
            ReadingRecommendationExport.model_validate(r) for r in reading_recommendations
        ],
        reading_allowlist=[ReadingAllowlistExport.model_validate(r) for r in reading_allowlist],
        weekly_projects=[WeeklyProjectExport.model_validate(r) for r in weekly_projects],
        project_tasks=[ProjectTaskExport.model_validate(r) for r in project_tasks],
        project_evaluations=[
            ProjectEvaluationExport.model_validate(r) for r in project_evaluations
        ],
        feedback=[FeedbackExport.model_validate(r) for r in feedback],
        triage_items=[TriageItemExport.model_validate(r) for r in triage_items],
        user_settings=[UserSettingsExport.model_validate(r) for r in user_settings],
        onboarding_state=[OnboardingStateExport.model_validate(r) for r in onboarding_state],
    )

    logger.info(
        "Exported %d journal entries, %d topics, %d quiz sessions, %d projects",
        len(bundle.journal_entries),
        len(bundle.topics),
        len(bundle.quiz_sessions),
        len(bundle.weekly_projects),
    )
    return bundle


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

# Deletion order: children first, then parents (reverse FK dependency).
_DELETE_ORDER = [
    QuizEvaluation,
    QuizAnswer,
    QuizQuestion,
    QuizSession,
    ProjectEvaluation,
    ProjectTask,
    WeeklyProject,
    ReadingRecommendation,
    ReadingAllowlist,
    TopicRelationship,
    Feedback,
    TriageItem,
    JournalEntryVersion,
    JournalEntry,
    ProfileSnapshot,
    OnboardingState,
    UserSettings,
    Topic,
]


def _to_model(model_cls, data: dict):
    """Instantiate an ORM model from an export dict, ignoring unknown keys."""
    cols = {c.key for c in model_cls.__table__.columns}
    # Handle the metadata_ / metadata alias on WeeklyProject
    if model_cls is WeeklyProject and "metadata_" in data:
        data["metadata_"] = data.pop("metadata_", None)
    filtered = {k: v for k, v in data.items() if k in cols}
    return model_cls(**filtered)


# Tables checked when deciding whether the DB is "populated".
_SENTINEL_TABLES = [JournalEntry, Topic, QuizSession, WeeklyProject]


async def is_database_populated(db: AsyncSession) -> dict[str, int]:
    """Return row counts for key tables. Non-zero means data exists."""
    counts: dict[str, int] = {}
    for model in _SENTINEL_TABLES:
        result = await db.execute(
            select(func.count("*")).select_from(model)  # type: ignore[arg-type]
        )
        counts[model.__tablename__] = result.scalar_one()
    return counts


async def import_all(
    db: AsyncSession,
    bundle: DataExportBundle,
    *,
    confirm_overwrite: bool = False,
) -> ImportResult:
    """Replace all data with the contents of *bundle*.

    This is a destructive operation — existing data is deleted first so that
    UUID primary keys from the source machine are preserved exactly.

    If the database already contains data, *confirm_overwrite* must be
    ``True`` or a ``ValueError`` is raised to prevent accidental data loss.
    """
    # 0. Safety check: reject if the DB is populated and the caller didn't
    #    explicitly acknowledge the overwrite.
    existing = await is_database_populated(db)
    if any(v > 0 for v in existing.values()) and not confirm_overwrite:
        populated = {k: v for k, v in existing.items() if v > 0}
        raise ValueError(
            f"Database already contains data ({populated}). "
            "Pass confirm_overwrite=true to replace it."
        )

    # 1. Delete everything (children first).
    for model in _DELETE_ORDER:
        await db.execute(delete(model))
    await db.flush()

    counts: dict[str, int] = {}

    # 2. Insert in parent-first order so FK constraints are satisfied.

    # --- Topics (self-referential: insert with parent_topic_id=None first, patch after)
    topic_dicts = [t.model_dump() for t in bundle.topics]
    parent_map: dict[str, str | None] = {}
    for td in topic_dicts:
        parent_map[str(td["id"])] = td.get("parent_topic_id")
        td["parent_topic_id"] = None  # break self-FK for initial insert
    for td in topic_dicts:
        db.add(_to_model(Topic, td))
    await db.flush()
    # Now set parent_topic_id in a second pass
    for tid, pid in parent_map.items():
        if pid is not None:
            topic = await db.get(Topic, tid)
            if topic:
                topic.parent_topic_id = pid
    await db.flush()
    counts["topics"] = len(topic_dicts)

    # --- Topic relationships
    for item in bundle.topic_relationships:
        db.add(_to_model(TopicRelationship, item.model_dump()))
    counts["topic_relationships"] = len(bundle.topic_relationships)

    # --- Journal entries + versions
    for item in bundle.journal_entries:
        db.add(_to_model(JournalEntry, item.model_dump()))
    await db.flush()
    for item in bundle.journal_entry_versions:
        db.add(_to_model(JournalEntryVersion, item.model_dump()))
    counts["journal_entries"] = len(bundle.journal_entries)
    counts["journal_entry_versions"] = len(bundle.journal_entry_versions)

    # --- Quiz sessions → questions → answers / evaluations
    for item in bundle.quiz_sessions:
        db.add(_to_model(QuizSession, item.model_dump()))
    await db.flush()
    for item in bundle.quiz_questions:
        db.add(_to_model(QuizQuestion, item.model_dump()))
    await db.flush()
    for item in bundle.quiz_answers:
        db.add(_to_model(QuizAnswer, item.model_dump()))
    for item in bundle.quiz_evaluations:
        db.add(_to_model(QuizEvaluation, item.model_dump()))
    counts["quiz_sessions"] = len(bundle.quiz_sessions)
    counts["quiz_questions"] = len(bundle.quiz_questions)
    counts["quiz_answers"] = len(bundle.quiz_answers)
    counts["quiz_evaluations"] = len(bundle.quiz_evaluations)

    # --- Readings
    for item in bundle.reading_recommendations:
        db.add(_to_model(ReadingRecommendation, item.model_dump()))
    for item in bundle.reading_allowlist:
        db.add(_to_model(ReadingAllowlist, item.model_dump()))
    counts["reading_recommendations"] = len(bundle.reading_recommendations)
    counts["reading_allowlist"] = len(bundle.reading_allowlist)

    # --- Projects → tasks → evaluations
    for item in bundle.weekly_projects:
        db.add(_to_model(WeeklyProject, item.model_dump()))
    await db.flush()
    for item in bundle.project_tasks:
        db.add(_to_model(ProjectTask, item.model_dump()))
    for item in bundle.project_evaluations:
        db.add(_to_model(ProjectEvaluation, item.model_dump()))
    counts["weekly_projects"] = len(bundle.weekly_projects)
    counts["project_tasks"] = len(bundle.project_tasks)
    counts["project_evaluations"] = len(bundle.project_evaluations)

    # --- Feedback, triage, settings, onboarding, snapshots
    for item in bundle.feedback:
        db.add(_to_model(Feedback, item.model_dump()))
    counts["feedback"] = len(bundle.feedback)

    for item in bundle.triage_items:
        db.add(_to_model(TriageItem, item.model_dump()))
    counts["triage_items"] = len(bundle.triage_items)

    for item in bundle.user_settings:
        db.add(_to_model(UserSettings, item.model_dump()))
    counts["user_settings"] = len(bundle.user_settings)

    for item in bundle.onboarding_state:
        db.add(_to_model(OnboardingState, item.model_dump()))
    counts["onboarding_state"] = len(bundle.onboarding_state)

    for item in bundle.profile_snapshots:
        db.add(_to_model(ProfileSnapshot, item.model_dump()))
    counts["profile_snapshots"] = len(bundle.profile_snapshots)

    await db.flush()

    total = sum(counts.values())
    logger.info("Imported %d total rows across %d tables", total, len(counts))

    return ImportResult(
        message=f"Successfully imported {total} rows across {len(counts)} tables.",
        counts=counts,
    )
