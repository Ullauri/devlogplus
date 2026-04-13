"""Topic and Knowledge Profile schemas."""

import uuid
from datetime import datetime

from pydantic import Field

from backend.app.models.base import (
    EvidenceStrength,
    TopicCategory,
    TopicRelationshipType,
)
from backend.app.schemas.common import BaseSchema


# ---------------------------------------------------------------------------
# Topic
# ---------------------------------------------------------------------------
class TopicResponse(BaseSchema):
    """A single topic in the Knowledge Profile."""

    id: uuid.UUID = Field(description="Topic ID")
    name: str = Field(description="Topic name (e.g. 'Go concurrency patterns')")
    description: str | None = Field(description="AI-generated description of the topic")
    category: TopicCategory = Field(
        description="Topic category (language, framework, concept, tool, etc.)"
    )
    evidence_strength: EvidenceStrength = Field(
        description=(
            "How much evidence supports this topic: "
            "strong, developing, or limited. Limited ≠ weakness."
        )
    )
    confidence: float = Field(
        description="System confidence in this assessment (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )
    evidence_summary: dict | None = Field(
        description="Structured evidence supporting this topic assessment (JSONB)"
    )
    parent_topic_id: uuid.UUID | None = Field(
        description="ID of parent topic, if this is a sub-topic"
    )
    created_at: datetime = Field(description="When the topic was first identified")
    updated_at: datetime = Field(description="When the topic was last updated")


class TopicRelationshipResponse(BaseSchema):
    """A directed relationship between two topics."""

    id: uuid.UUID = Field(description="Relationship ID")
    source_topic_id: uuid.UUID = Field(description="Source topic ID")
    target_topic_id: uuid.UUID = Field(description="Target topic ID")
    relationship_type: TopicRelationshipType = Field(
        description="Type of relationship (prerequisite, related, extends)"
    )
    confidence: float = Field(
        description="Confidence in this relationship (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )


class TopicDetailResponse(TopicResponse):
    """Topic with its incoming and outgoing relationships."""

    outgoing_relationships: list[TopicRelationshipResponse] = Field(
        default=[], description="Relationships where this topic is the source"
    )
    incoming_relationships: list[TopicRelationshipResponse] = Field(
        default=[], description="Relationships where this topic is the target"
    )


# ---------------------------------------------------------------------------
# Knowledge Profile (aggregated view)
# ---------------------------------------------------------------------------
class KnowledgeProfileResponse(BaseSchema):
    """The full Knowledge Profile — an AI-derived, read-only view of the user's
    technical knowledge organized by evidence strength and learning state."""

    strengths: list[TopicResponse] = Field(default=[], description="Topics with strong evidence")
    weak_spots: list[TopicResponse] = Field(default=[], description="Topics with limited evidence")
    current_frontier: list[TopicResponse] = Field(
        default=[],
        description="Topics the user is actively learning or partially understands",
    )
    next_frontier: list[TopicResponse] = Field(
        default=[],
        description="Adjacent topics the system recommends exploring next",
    )
    recurring_themes: list[TopicResponse] = Field(
        default=[], description="Frequently mentioned topics across journal entries"
    )
    unresolved: list[TopicResponse] = Field(
        default=[], description="Topics pending triage resolution"
    )
    total_topics: int = Field(0, description="Total number of topics in the profile")
    last_updated: datetime | None = Field(
        None, description="When the profile was last updated by the nightly pipeline"
    )


class ProfileSnapshotResponse(BaseSchema):
    """A historical snapshot of the Knowledge Profile at a point in time."""

    id: uuid.UUID = Field(description="Snapshot ID")
    snapshot_data: dict = Field(
        description="Full profile state serialised as JSON at snapshot time"
    )
    trigger: str = Field(description="What triggered this snapshot (e.g. 'nightly_update')")
    created_at: datetime = Field(description="When the snapshot was taken")
