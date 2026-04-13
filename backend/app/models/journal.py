"""Journal entry and version models."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin, UUIDMixin


class JournalEntry(Base, UUIDMixin, TimestampMixin):
    """A journal entry. Versions are append-only; most recent is source of truth."""

    __tablename__ = "journal_entries"

    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_processed: Mapped[bool] = mapped_column(default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    versions: Mapped[list["JournalEntryVersion"]] = relationship(
        back_populates="entry",
        order_by="JournalEntryVersion.version_number",
        cascade="all, delete-orphan",
    )


class JournalEntryVersion(Base, UUIDMixin):
    """A single version of a journal entry. Append-only."""

    __tablename__ = "journal_entry_versions"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # pgvector embedding for semantic search
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)

    # Relationships
    entry: Mapped["JournalEntry"] = relationship(back_populates="versions")
