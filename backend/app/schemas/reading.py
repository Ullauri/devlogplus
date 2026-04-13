"""Reading recommendation and allowlist schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from backend.app.models.base import ReadingRecommendationType
from backend.app.schemas.common import BaseSchema


# ---------------------------------------------------------------------------
# Reading Recommendation
# ---------------------------------------------------------------------------
class ReadingRecommendationResponse(BaseSchema):
    """A curated reading recommendation generated from the Knowledge Profile."""

    id: uuid.UUID = Field(description="Recommendation ID")
    title: str = Field(
        description="Title of the recommended article or resource",
        examples=["Understanding Go's Concurrency Model"],
    )
    url: str = Field(
        description="Full URL to the recommended resource",
        examples=["https://go.dev/blog/concurrency-is-not-parallelism"],
    )
    source_domain: str = Field(
        description="Domain the URL belongs to (must be on the allowlist)",
        examples=["go.dev"],
    )
    description: str | None = Field(
        description="Brief AI-generated summary of why this was recommended"
    )
    topic_id: uuid.UUID | None = Field(
        description="Knowledge Profile topic this recommendation relates to"
    )
    recommendation_type: ReadingRecommendationType = Field(
        description="Type of recommendation (deepening, broadening, refresher)"
    )
    batch_date: date = Field(description="The weekly batch date this recommendation belongs to")
    created_at: datetime = Field(description="When the recommendation was generated")
    updated_at: datetime = Field(description="Last modification timestamp")


# ---------------------------------------------------------------------------
# Reading Allowlist
# ---------------------------------------------------------------------------
class AllowlistEntryCreate(BaseModel):
    """Add a domain to the reading allowlist.

    Only domains on the allowlist will be used for reading recommendations.
    """

    domain: str = Field(
        ...,
        min_length=1,
        description="Domain name (e.g. 'go.dev', 'docs.python.org')",
        examples=["go.dev"],
    )
    name: str = Field(
        ...,
        min_length=1,
        description="Human-friendly label for the domain",
        examples=["Go Official Blog"],
    )
    description: str | None = Field(
        None, description="Optional description of what this source provides"
    )


class AllowlistEntryUpdate(BaseModel):
    """Update an existing allowlist entry's name or description."""

    name: str | None = Field(None, description="Updated label (null to keep current)")
    description: str | None = Field(None, description="Updated description (null to keep current)")


class AllowlistEntryResponse(BaseSchema):
    """A domain on the reading recommendation allowlist."""

    id: uuid.UUID = Field(description="Entry ID")
    domain: str = Field(description="Allowlisted domain name")
    name: str = Field(description="Human-friendly label")
    description: str | None = Field(description="Optional description")
    is_default: bool = Field(
        description="Whether this is a built-in default entry (cannot be deleted)"
    )
    created_at: datetime = Field(description="When the entry was added")
