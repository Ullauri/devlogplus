"""Journal entry schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.schemas.common import BaseSchema


# ---------------------------------------------------------------------------
# Journal Entry Version
# ---------------------------------------------------------------------------
class JournalEntryVersionResponse(BaseSchema):
    """A single version of a journal entry's content."""

    id: uuid.UUID = Field(description="Version ID")
    entry_id: uuid.UUID = Field(description="Parent journal entry ID")
    content: str = Field(description="Full text content of this version")
    version_number: int = Field(description="Sequential version number (1-based)")
    is_current: bool = Field(description="Whether this is the latest version")
    created_at: datetime = Field(description="When this version was created")


# ---------------------------------------------------------------------------
# Journal Entry
# ---------------------------------------------------------------------------
class JournalEntryCreate(BaseModel):
    """Create a new journal entry.

    Content is text-only and can be typed or dictated via the browser
    Web Speech API.  Title is optional.
    """

    title: str | None = Field(
        None,
        description="Optional short title for the entry",
        examples=["Learning Go concurrency patterns"],
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Entry content (text only, no HTML)",
        examples=[
            "Today I explored Go channels and goroutines. The select statement "
            "is particularly powerful for multiplexing channel operations."
        ],
    )


class JournalEntryUpdate(BaseModel):
    """Edit an existing entry — creates a new version, preserving history."""

    title: str | None = Field(None, description="Updated title (null leaves unchanged)")
    content: str = Field(
        ...,
        min_length=1,
        description="Updated content (will become the new current version)",
    )


class JournalEntryResponse(BaseSchema):
    """Journal entry summary (without version history)."""

    id: uuid.UUID = Field(description="Entry ID")
    title: str | None = Field(description="Optional title")
    is_processed: bool = Field(description="Whether the nightly pipeline has processed this entry")
    processed_at: datetime | None = Field(
        description="When the entry was last processed by the pipeline"
    )
    created_at: datetime = Field(description="When the entry was first created")
    updated_at: datetime = Field(description="When the entry was last modified")
    current_content: str | None = Field(None, description="Content from the most recent version")


class JournalEntryDetailResponse(JournalEntryResponse):
    """Full journal entry with append-only version history."""

    versions: list[JournalEntryVersionResponse] = Field(
        default=[],
        description="All versions of this entry, ordered by version number",
    )
