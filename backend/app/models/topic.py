"""Topic and topic relationship models."""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import (
    Base,
    EvidenceStrength,
    TimestampMixin,
    TopicCategory,
    TopicRelationshipType,
    UUIDMixin,
)


class Topic(Base, UUIDMixin, TimestampMixin):
    """An atomic unit of the Knowledge Profile, dynamically derived by LLM."""

    __tablename__ = "topics"

    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[TopicCategory] = mapped_column(nullable=False)
    evidence_strength: Mapped[EvidenceStrength] = mapped_column(
        nullable=False, default=EvidenceStrength.LIMITED
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    evidence_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    parent_topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
    )

    # pgvector embedding for topic matching
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)

    # Relationships
    parent_topic: Mapped["Topic | None"] = relationship(
        remote_side="Topic.id",
        backref="subtopics",
    )
    outgoing_relationships: Mapped[list["TopicRelationship"]] = relationship(
        foreign_keys="TopicRelationship.source_topic_id",
        back_populates="source_topic",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[list["TopicRelationship"]] = relationship(
        foreign_keys="TopicRelationship.target_topic_id",
        back_populates="target_topic",
        cascade="all, delete-orphan",
    )


class TopicRelationship(Base, UUIDMixin):
    """A relationship between two topics (adjacent, prerequisite, subtopic)."""

    __tablename__ = "topic_relationships"

    source_topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[TopicRelationshipType] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    # Relationships
    source_topic: Mapped["Topic"] = relationship(
        foreign_keys=[source_topic_id],
        back_populates="outgoing_relationships",
    )
    target_topic: Mapped["Topic"] = relationship(
        foreign_keys=[target_topic_id],
        back_populates="incoming_relationships",
    )
