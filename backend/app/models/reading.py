"""Reading recommendation and allowlist models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.functions import now

from backend.app.models.base import (
    Base,
    ReadingRecommendationType,
    TimestampMixin,
    UUIDMixin,
)

if TYPE_CHECKING:
    from backend.app.models.topic import Topic  # noqa: F401


class ReadingRecommendation(Base, UUIDMixin, TimestampMixin):
    """A curated reading recommendation from the allowlist."""

    __tablename__ = "reading_recommendations"

    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_domain: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
    )
    recommendation_type: Mapped[ReadingRecommendationType] = mapped_column(nullable=False)
    batch_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Per-item user state.  Each is a nullable timestamp rather than a status
    # enum so we record *when* the action happened (useful for engagement
    # metrics feeding back into profile_update / reading_generation).
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    topic: Mapped[Topic | None] = relationship()

    @property
    def status(self) -> str:
        """Derived single-value status for UI consumption.

        Priority: dismissed > read > saved > unread.  A "saved-then-read"
        item surfaces as ``read`` because that's the more informative signal
        for the recommendations UI.
        """
        if self.dismissed_at is not None:
            return "dismissed"
        if self.read_at is not None:
            return "read"
        if self.saved_at is not None:
            return "saved"
        return "unread"


class ReadingAllowlist(Base, UUIDMixin):
    """An approved source domain for reading recommendations."""

    __tablename__ = "reading_allowlist"

    domain: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=now(),
        nullable=False,
    )
