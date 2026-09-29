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
from backend.app.models.base import FeedbackTargetType, TriageSource
from backend.app.schemas.transfer import (
    CURRENT_FORMAT_VERSION,
    DataExportBundle,
    FeedbackExport,
    ImportResult,
    JournalEntryExport,
    JournalEntryVersionExport,
    OnboardingStateExport,
    ProfileSnapshotExport,
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
)

logger = logging.getLogger(__name__)

APP_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

_EXPORT_TABLES: list[type] = [
    JournalEntry,
    JournalEntryVersion,
    Topic,
    TopicRelationship,
    ProfileSnapshot,
    QuizSession,
    QuizQuestion,
    QuizAnswer,
    QuizEvaluation,
    ReadingRecommendation,
    ReadingAllowlist,
    Feedback,
    TriageItem,
    UserSettings,
    OnboardingState,
]

# Feedback targets and triage sources that only make sense next to a project.
# Projects do not transfer (see `DataExportBundle`), so exporting these would
# move a thumbs-down whose subject is not there to read, pointing at a
# `target_id` that resolves to nothing on the new machine.
_PROJECT_FEEDBACK_TARGETS = frozenset({FeedbackTargetType.PROJECT, FeedbackTargetType.PROJECT_TASK})


async def count_tables(db: AsyncSession) -> dict[str, int]:
    """Return per-table row counts using COUNT(*) — no rows are fetched."""
    counts: dict[str, int] = {}
    for model in _EXPORT_TABLES:
        result = await db.execute(select(func.count()).select_from(model))
        counts[model.__tablename__] = result.scalar_one()
    return counts


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
    feedback = [r for r in await _all(Feedback) if r.target_type not in _PROJECT_FEEDBACK_TARGETS]
    triage_items = [
        r for r in await _all(TriageItem) if r.source != TriageSource.PROJECT_EVALUATION
    ]
    user_settings = await _all(UserSettings)
    onboarding_state = await _all(OnboardingState)

    bundle = DataExportBundle(
        format_version=CURRENT_FORMAT_VERSION,
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
        feedback=[FeedbackExport.model_validate(r) for r in feedback],
        triage_items=[TriageItemExport.model_validate(r) for r in triage_items],
        user_settings=[UserSettingsExport.model_validate(r) for r in user_settings],
        onboarding_state=[OnboardingStateExport.model_validate(r) for r in onboarding_state],
    )

    logger.info(
        "Exported %d journal entries, %d topics, %d quiz sessions (projects excluded)",
        len(bundle.journal_entries),
        len(bundle.topics),
        len(bundle.quiz_sessions),
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
    dropped = {k for k in data if k not in cols}
    if dropped:
        logger.debug(
            "Dropping unknown keys during import into %s: %s",
            model_cls.__tablename__,
            sorted(dropped),
        )
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


def _add_all(db: AsyncSession, model_cls, items) -> int:
    """Add one ORM row per exported item, in order. Returns how many were added."""
    for item in items:
        db.add(_to_model(model_cls, item.model_dump()))
    return len(items)


async def _import_topics(db: AsyncSession, topics) -> int:
    """Insert topics, then restore their self-referential parent links.

    Every topic is inserted with ``parent_topic_id=None`` first, so the
    self-FK never points at a row that does not exist yet, then patched.
    """
    topic_dicts = [t.model_dump() for t in topics]
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
    return len(topic_dicts)


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
    counts["topics"] = await _import_topics(db, bundle.topics)

    # --- Topic relationships
    counts["topic_relationships"] = _add_all(db, TopicRelationship, bundle.topic_relationships)

    # --- Journal entries + versions
    journal_entries = _add_all(db, JournalEntry, bundle.journal_entries)
    await db.flush()
    counts["journal_entries"] = journal_entries
    counts["journal_entry_versions"] = _add_all(
        db, JournalEntryVersion, bundle.journal_entry_versions
    )

    # --- Quiz sessions → questions → answers / evaluations
    counts["quiz_sessions"] = _add_all(db, QuizSession, bundle.quiz_sessions)
    await db.flush()
    counts["quiz_questions"] = _add_all(db, QuizQuestion, bundle.quiz_questions)
    await db.flush()
    counts["quiz_answers"] = _add_all(db, QuizAnswer, bundle.quiz_answers)
    counts["quiz_evaluations"] = _add_all(db, QuizEvaluation, bundle.quiz_evaluations)

    # --- Readings
    counts["reading_recommendations"] = _add_all(
        db, ReadingRecommendation, bundle.reading_recommendations
    )
    counts["reading_allowlist"] = _add_all(db, ReadingAllowlist, bundle.reading_allowlist)

    # --- Projects are dropped, not restored.
    # Step 1 already deleted them, and nothing re-inserts them: the Go code a
    # project row points at lives on the old machine's disk, so restoring the
    # row would leave a project whose `project_path` resolves to nothing.
    # Counted at zero rather than omitted, so the summary shows the decision
    # was made rather than leaving the reader to wonder.
    skipped = (
        len(bundle.weekly_projects) + len(bundle.project_tasks) + len(bundle.project_evaluations)
    )
    if skipped:
        logger.info(
            "Skipped %d project row(s) from a format_version %d bundle — "
            "projects do not transfer between machines.",
            skipped,
            bundle.format_version,
        )
    counts["weekly_projects"] = 0
    counts["project_tasks"] = 0
    counts["project_evaluations"] = 0

    # --- Feedback, triage, settings, onboarding, snapshots
    # A format_version 1 bundle predates the project exclusion and still
    # carries signals about projects. Filtered here for the same reason export
    # filters them: without the project they point at, a thumbs-down on a task
    # nobody can open is noise the new machine cannot act on.
    kept_feedback = [f for f in bundle.feedback if f.target_type not in _PROJECT_FEEDBACK_TARGETS]
    counts["feedback"] = _add_all(db, Feedback, kept_feedback)

    kept_triage = [t for t in bundle.triage_items if t.source != TriageSource.PROJECT_EVALUATION]
    counts["triage_items"] = _add_all(db, TriageItem, kept_triage)

    counts["user_settings"] = _add_all(db, UserSettings, bundle.user_settings)
    counts["onboarding_state"] = _add_all(db, OnboardingState, bundle.onboarding_state)
    counts["profile_snapshots"] = _add_all(db, ProfileSnapshot, bundle.profile_snapshots)

    await db.flush()

    total = sum(counts.values())
    logger.info("Imported %d total rows across %d tables", total, len(counts))

    return ImportResult(
        message=f"Successfully imported {total} rows across {len(counts)} tables.",
        counts=counts,
    )
