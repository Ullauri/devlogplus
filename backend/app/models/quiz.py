"""Quiz session, question, answer, and evaluation models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.functions import now

from backend.app.models.base import (
    Base,
    QuizCorrectness,
    QuizQuestionType,
    QuizSessionStatus,
    TimestampMixin,
    UUIDMixin,
)

if TYPE_CHECKING:
    from backend.app.models.topic import Topic


class QuizSession(Base, UUIDMixin, TimestampMixin):
    """A weekly quiz session containing multiple questions."""

    __tablename__ = "quiz_sessions"

    status: Mapped[QuizSessionStatus] = mapped_column(
        nullable=False, default=QuizSessionStatus.PENDING
    )
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="session",
        order_by="QuizQuestion.order_index",
        cascade="all, delete-orphan",
    )


class QuizQuestion(Base, UUIDMixin):
    """A single quiz question within a session."""

    __tablename__ = "quiz_questions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quiz_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[QuizQuestionType] = mapped_column(nullable=False)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=now(),
        nullable=False,
    )

    # Relationships
    session: Mapped["QuizSession"] = relationship(back_populates="questions")
    answer: Mapped["QuizAnswer | None"] = relationship(
        back_populates="question", uselist=False, cascade="all, delete-orphan"
    )
    evaluation: Mapped["QuizEvaluation | None"] = relationship(
        back_populates="question", uselist=False, cascade="all, delete-orphan"
    )
    topic: Mapped["Topic | None"] = relationship("Topic", lazy="joined", foreign_keys=[topic_id])

    @property
    def topic_name(self) -> str | None:
        """Convenience accessor used by response schemas.

        Reads the eager/joined-loaded ``topic`` relationship; returns ``None``
        when the question is not linked to a Knowledge Profile topic.
        """
        return self.topic.name if self.topic is not None else None


class QuizAnswer(Base, UUIDMixin):
    """The user's free-text answer to a quiz question."""

    __tablename__ = "quiz_answers"

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quiz_questions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=now(),
        nullable=False,
    )

    # Relationships
    question: Mapped["QuizQuestion"] = relationship(back_populates="answer")


class QuizEvaluation(Base, UUIDMixin):
    """LLM evaluation of a quiz answer."""

    __tablename__ = "quiz_evaluations"

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quiz_questions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    correctness: Mapped[QuizCorrectness] = mapped_column(nullable=False)
    depth_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    raw_llm_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=now(),
        nullable=False,
    )

    # Relationships
    question: Mapped["QuizQuestion"] = relationship(back_populates="evaluation")
