"""SQLAlchemy declarative base, mixins, and shared enums."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# Enums (defined BEFORE ``Base`` so they can be referenced in
# ``Base.type_annotation_map`` — see note there).
# ---------------------------------------------------------------------------
class EvidenceStrength(enum.StrEnum):
    STRONG = "strong"
    DEVELOPING = "developing"
    LIMITED = "limited"


class TopicCategory(enum.StrEnum):
    DEMONSTRATED_STRENGTH = "demonstrated_strength"
    WEAK_SPOT = "weak_spot"
    CURRENT_FRONTIER = "current_frontier"
    NEXT_FRONTIER = "next_frontier"
    RECURRING_THEME = "recurring_theme"
    UNRESOLVED = "unresolved"


class TopicRelationshipType(enum.StrEnum):
    ADJACENT = "adjacent"
    PREREQUISITE = "prerequisite"
    SUBTOPIC = "subtopic"


class QuizSessionStatus(enum.StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EVALUATED = "evaluated"


class QuizQuestionType(enum.StrEnum):
    REINFORCEMENT = "reinforcement"
    EXPLORATION = "exploration"


class QuizCorrectness(enum.StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    INCORRECT = "incorrect"


class ReadingRecommendationType(enum.StrEnum):
    NEXT_FRONTIER = "next_frontier"
    WEAK_SPOT = "weak_spot"
    DEEP_DIVE = "deep_dive"


class ProjectStatus(enum.StrEnum):
    ISSUED = "issued"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    EVALUATED = "evaluated"
    SKIPPED = "skipped"


class ProjectTaskType(enum.StrEnum):
    BUG_FIX = "bug_fix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    OPTIMIZATION = "optimization"


class TriageSource(enum.StrEnum):
    PROFILE_UPDATE = "profile_update"
    QUIZ_EVALUATION = "quiz_evaluation"
    PROJECT_EVALUATION = "project_evaluation"


class TriageSeverity(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TriageStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"
    DEFERRED = "deferred"


class FeedbackTargetType(enum.StrEnum):
    QUIZ_QUESTION = "quiz_question"
    READING = "reading"
    PROJECT = "project"
    PROJECT_TASK = "project_task"


class FeedbackReaction(enum.StrEnum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class PipelineType(enum.StrEnum):
    PROFILE_UPDATE = "profile_update"
    QUIZ_GENERATION = "quiz_generation"
    QUIZ_EVALUATION = "quiz_evaluation"
    READING_GENERATION = "reading_generation"
    PROJECT_GENERATION = "project_generation"
    PROJECT_EVALUATION = "project_evaluation"
    TOPIC_EXTRACTION = "topic_extraction"


class PipelineStatus(enum.StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


def _string_enum(cls: type[enum.Enum]) -> SAEnum:
    """Build a ``sa.Enum`` backed by VARCHAR (no PG native ENUM type).

    Our Alembic migrations store these columns as ``TEXT``. The SQLAlchemy 2.0
    default for ``Mapped[SomeEnum]`` would create (and ``::cast`` to) a native
    PostgreSQL enum type like ``quizsessionstatus`` — a type that does not
    exist in the migrated schema, producing ``UndefinedObjectError`` at
    runtime. Forcing ``native_enum=False`` keeps the wire format as strings,
    matching the migrations.
    """
    return SAEnum(
        cls,
        native_enum=False,
        create_constraint=False,
        length=50,
        validate_strings=True,
    )


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models.

    ``type_annotation_map`` rewrites every ``Mapped[SomeEnum]`` column to use
    a non-native ``sa.Enum`` (VARCHAR), matching how the Alembic migrations
    store these columns as ``TEXT``. Without this, SQLAlchemy would emit
    ``::quizsessionstatus`` / ``::pipelinetype`` casts against PG enum types
    that the migrations never create — producing ``UndefinedObjectError`` at
    runtime.
    """

    type_annotation_map = {  # noqa: RUF012 — SQLAlchemy reads this as a ClassVar
        EvidenceStrength: _string_enum(EvidenceStrength),
        TopicCategory: _string_enum(TopicCategory),
        TopicRelationshipType: _string_enum(TopicRelationshipType),
        QuizSessionStatus: _string_enum(QuizSessionStatus),
        QuizQuestionType: _string_enum(QuizQuestionType),
        QuizCorrectness: _string_enum(QuizCorrectness),
        ReadingRecommendationType: _string_enum(ReadingRecommendationType),
        ProjectStatus: _string_enum(ProjectStatus),
        ProjectTaskType: _string_enum(ProjectTaskType),
        TriageSource: _string_enum(TriageSource),
        TriageSeverity: _string_enum(TriageSeverity),
        TriageStatus: _string_enum(TriageStatus),
        FeedbackTargetType: _string_enum(FeedbackTargetType),
        FeedbackReaction: _string_enum(FeedbackReaction),
        PipelineType: _string_enum(PipelineType),
        PipelineStatus: _string_enum(PipelineStatus),
    }


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------
class UUIDMixin:
    """Provides a UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Provides created_at and updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )
