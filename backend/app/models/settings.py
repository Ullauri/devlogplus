"""User settings, onboarding state, and processing log models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import (
    Base,
    PipelineStatus,
    PipelineType,
    UUIDMixin,
)


class UserSettings(Base, UUIDMixin):
    """Key-value application settings (single user)."""

    __tablename__ = "user_settings"

    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OnboardingState(Base, UUIDMixin):
    """Tracks the first-run onboarding flow state."""

    __tablename__ = "onboarding_state"

    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    self_assessment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    go_experience_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostic_quiz_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    topic_interests: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ProfileSnapshot(Base, UUIDMixin):
    """A point-in-time snapshot of the Knowledge Profile."""

    __tablename__ = "profile_snapshots"

    snapshot_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False, default="nightly_update")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ProcessingLog(Base, UUIDMixin):
    """Tracks pipeline execution history."""

    __tablename__ = "processing_logs"

    pipeline: Mapped[PipelineType] = mapped_column(nullable=False)
    status: Mapped[PipelineStatus] = mapped_column(nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
