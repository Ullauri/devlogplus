"""SQLAlchemy declarative base, mixins, and shared enums."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


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
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Enums
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
