"""Feedback model — covers both feedback and feedforward signals."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import (
    Base,
    FeedbackReaction,
    FeedbackTargetType,
    UUIDMixin,
)


class Feedback(Base, UUIDMixin):
    """User feedback / feedforward on a generated item."""

    __tablename__ = "feedback"

    target_type: Mapped[FeedbackTargetType] = mapped_column(nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reaction: Mapped[FeedbackReaction | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
