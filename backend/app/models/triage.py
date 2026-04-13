"""Triage item model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import (
    Base,
    TimestampMixin,
    TriageSeverity,
    TriageSource,
    TriageStatus,
    UUIDMixin,
)


class TriageItem(Base, UUIDMixin, TimestampMixin):
    """An item requiring user attention due to system uncertainty."""

    __tablename__ = "triage_items"

    source: Mapped[TriageSource] = mapped_column(nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    severity: Mapped[TriageSeverity] = mapped_column(nullable=False)
    status: Mapped[TriageStatus] = mapped_column(nullable=False, default=TriageStatus.PENDING)
    resolution_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
