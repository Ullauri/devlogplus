"""Weekly project, task, and evaluation schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.models.base import ProjectStatus, ProjectTaskType
from backend.app.schemas.common import BaseSchema


# ---------------------------------------------------------------------------
# Project Task
# ---------------------------------------------------------------------------
class ProjectTaskResponse(BaseSchema):
    """A single task within a weekly project (bug fix, feature, refactor, etc.)."""

    id: uuid.UUID = Field(description="Task ID")
    project_id: uuid.UUID = Field(description="Parent project ID")
    title: str = Field(
        description="Short task title",
        examples=["Fix goroutine leak in worker pool"],
    )
    description: str = Field(description="Detailed task description with acceptance criteria")
    task_type: ProjectTaskType = Field(
        description="Task type: bug, feature, refactor, or optimization"
    )
    order_index: int = Field(description="Display order within the project (0-based)")
    created_at: datetime = Field(description="When the task was generated")


# ---------------------------------------------------------------------------
# Project Evaluation
# ---------------------------------------------------------------------------
class ProjectEvaluationResponse(BaseSchema):
    """AI-generated evaluation of a submitted project."""

    id: uuid.UUID = Field(description="Evaluation ID")
    project_id: uuid.UUID = Field(description="The project this evaluation applies to")
    code_quality_score: float = Field(
        description="Overall code quality score (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )
    task_completion: dict = Field(description="Per-task completion status and assessment (JSONB)")
    test_results: dict | None = Field(
        description="Summary of test execution results, if tests were run (JSONB)"
    )
    overall_assessment: str = Field(description="Free-text overall assessment of the submission")
    confidence: float = Field(
        description="LLM confidence in this evaluation (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )
    created_at: datetime = Field(description="When the evaluation was generated")


# ---------------------------------------------------------------------------
# Weekly Project
# ---------------------------------------------------------------------------
class ProjectSubmitRequest(BaseModel):
    """Submit a completed project for AI evaluation."""

    notes: str | None = Field(
        None,
        description="Optional notes about the submission (e.g. challenges faced, shortcuts taken)",
        examples=["Focused on the refactor task first; ran out of time on the optimization."],
    )


class WeeklyProjectResponse(BaseSchema):
    """Weekly Go project summary."""

    id: uuid.UUID = Field(description="Project ID")
    title: str = Field(description="Project title", examples=["HTTP Rate Limiter"])
    description: str = Field(description="Project overview and goals")
    difficulty_level: int = Field(
        description="Difficulty level (1–5), calibrated to the user's profile",
        ge=1,
        le=5,
    )
    project_path: str = Field(
        description="Filesystem path to the generated project codebase",
        examples=["workspace/projects/2026-w15-rate-limiter"],
    )
    status: ProjectStatus = Field(description="Project status: issued, submitted, or evaluated")
    issued_at: datetime = Field(description="When the project was issued")
    submitted_at: datetime | None = Field(
        description="When the user submitted the project (null if not yet submitted)"
    )
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last modification timestamp")


class WeeklyProjectDetailResponse(WeeklyProjectResponse):
    """Project with tasks, metadata, and optional AI evaluation."""

    tasks: list[ProjectTaskResponse] = Field(
        default=[], description="Ordered list of tasks to complete"
    )
    evaluation: ProjectEvaluationResponse | None = Field(
        None, description="AI evaluation of the submission (null if not yet evaluated)"
    )
    metadata_: dict | None = Field(None, description="Additional project metadata (JSONB)")
