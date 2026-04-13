"""Triage item schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.models.base import TriageSeverity, TriageSource, TriageStatus
from backend.app.schemas.common import BaseSchema


class TriageResolveRequest(BaseModel):
    """Resolve a triage item with a user action and optional clarification text."""

    action: TriageStatus = Field(
        ...,
        description="Resolution action: accepted, rejected, edited, or deferred",
    )
    resolution_text: str | None = Field(
        None,
        description=(
            "Clarifying text from the user. Required when action is 'edited'; "
            "optional for other actions."
        ),
        examples=["The topic should be 'Go error handling' not 'Go exceptions'."],
    )


class TriageItemResponse(BaseSchema):
    """An item requiring user attention before the system can proceed."""

    id: uuid.UUID = Field(description="Triage item ID")
    source: TriageSource = Field(
        description="Pipeline that created this item "
        "(profile_update, quiz_evaluation, project_evaluation)"
    )
    source_id: uuid.UUID | None = Field(
        description="ID of the source entity (e.g. topic, quiz question) that triggered this item"
    )
    title: str = Field(description="Short title summarising the issue")
    description: str = Field(description="Detailed description of what needs resolution")
    context: dict | None = Field(description="Additional context from the pipeline (JSONB)")
    severity: TriageSeverity = Field(
        description="Severity: low, medium, high, or critical. High/critical block the next cycle."
    )
    status: TriageStatus = Field(
        description="Current status: pending, accepted, rejected, edited, or deferred"
    )
    resolution_text: str | None = Field(
        description="User's clarification text (populated after resolution)"
    )
    resolved_at: datetime | None = Field(
        description="When the item was resolved (null if still pending)"
    )
    created_at: datetime = Field(description="When the item was created")
    updated_at: datetime = Field(description="Last modification timestamp")
