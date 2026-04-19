"""Schemas for manually triggering and inspecting pipeline runs.

These endpoints expose a *user-initiated* escape hatch for running the
normally-scheduled pipelines (profile update, quiz/reading/project
generation) on demand — e.g. when the user doesn't want to wait for the
next cron invocation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.base import PipelineStatus, PipelineType
from backend.app.schemas.common import BaseSchema

# The pipelines that are safe to trigger as a single top-level "run".
# Evaluation pipelines (quiz_evaluation, project_evaluation, topic_extraction)
# are driven by user-submitted content and are not exposed here.
ManualPipelineName = Literal[
    "profile_update",
    "quiz_generation",
    "reading_generation",
    "project_generation",
]


class PipelineRunRequest(BaseModel):
    """Request body for a manual pipeline trigger (reserved for future options)."""

    # Kept intentionally empty for now; POST body is optional on the endpoints.
    model_config = {"extra": "forbid"}


class PipelineRunAccepted(BaseModel):
    """Response returned when a manual pipeline run is successfully queued."""

    pipeline: ManualPipelineName = Field(
        description="Name of the pipeline that was queued.",
    )
    run_id: uuid.UUID = Field(
        description=(
            "Unique identifier for this pipeline run. The same id appears in "
            "the corresponding `processing_logs` row, so clients (including "
            "AI agents) can poll `GET /pipelines/runs` and match progress to "
            "the run they just triggered."
        ),
    )
    status: Literal["queued"] = Field(
        default="queued",
        description="Always 'queued' — the run has been accepted for background execution.",
    )
    message: str = Field(
        description="Human-readable confirmation message.",
        examples=["Profile update pipeline queued. Check run history for progress."],
    )


class PipelineRunInfo(BaseSchema):
    """A single row from the processing_logs table, exposed for UI progress display."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    pipeline: PipelineType
    status: PipelineStatus
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    metadata: dict | None = Field(
        default=None,
        validation_alias="metadata_",
        description="Pipeline-specific summary metadata (counts, ids, etc.)",
    )
