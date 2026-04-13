"""Weekly project, task, and evaluation models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import (
    Base,
    ProjectStatus,
    ProjectTaskType,
    TimestampMixin,
    UUIDMixin,
)


class WeeklyProject(Base, UUIDMixin, TimestampMixin):
    """A generated weekly Go micro-project."""

    __tablename__ = "weekly_projects"

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    project_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(nullable=False, default=ProjectStatus.ISSUED)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    tasks: Mapped[list["ProjectTask"]] = relationship(
        back_populates="project",
        order_by="ProjectTask.order_index",
        cascade="all, delete-orphan",
    )
    evaluation: Mapped["ProjectEvaluation | None"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )


class ProjectTask(Base, UUIDMixin):
    """A specific task within a weekly project (bug fix, feature, refactor, etc.)."""

    __tablename__ = "project_tasks"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("weekly_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[ProjectTaskType] = mapped_column(nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["WeeklyProject"] = relationship(back_populates="tasks")


class ProjectEvaluation(Base, UUIDMixin):
    """LLM evaluation of a submitted project."""

    __tablename__ = "project_evaluations"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("weekly_projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    code_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    task_completion: Mapped[dict] = mapped_column(JSONB, nullable=False)
    test_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    overall_assessment: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    raw_llm_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["WeeklyProject"] = relationship(back_populates="evaluation")
