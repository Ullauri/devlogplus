"""Schemas for full data export / import (device-to-device transfer)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from backend.app.schemas.common import BaseSchema


# ---------------------------------------------------------------------------
# Per-table row schemas  (flat, JSON-friendly — no ORM relationships)
# ---------------------------------------------------------------------------
class JournalEntryExport(BaseSchema):
    id: uuid.UUID
    title: str | None
    is_processed: bool
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JournalEntryVersionExport(BaseSchema):
    id: uuid.UUID
    entry_id: uuid.UUID
    content: str
    version_number: int
    is_current: bool
    created_at: datetime


class TopicExport(BaseSchema):
    id: uuid.UUID
    name: str
    description: str | None
    category: str
    evidence_strength: str
    confidence: float
    evidence_summary: dict | None
    parent_topic_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class TopicRelationshipExport(BaseSchema):
    id: uuid.UUID
    source_topic_id: uuid.UUID
    target_topic_id: uuid.UUID
    relationship_type: str
    confidence: float


class QuizSessionExport(BaseSchema):
    id: uuid.UUID
    status: str
    question_count: int
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class QuizQuestionExport(BaseSchema):
    id: uuid.UUID
    session_id: uuid.UUID
    question_text: str
    question_type: str
    topic_id: uuid.UUID | None
    order_index: int
    created_at: datetime


class QuizAnswerExport(BaseSchema):
    id: uuid.UUID
    question_id: uuid.UUID
    answer_text: str
    created_at: datetime


class QuizEvaluationExport(BaseSchema):
    id: uuid.UUID
    question_id: uuid.UUID
    correctness: str
    depth_assessment: str | None
    explanation: str
    confidence: float
    raw_llm_output: dict | None
    created_at: datetime


class ReadingRecommendationExport(BaseSchema):
    id: uuid.UUID
    title: str
    url: str
    source_domain: str
    description: str | None
    topic_id: uuid.UUID | None
    recommendation_type: str
    batch_date: date
    created_at: datetime
    updated_at: datetime


class ReadingAllowlistExport(BaseSchema):
    id: uuid.UUID
    domain: str
    name: str
    description: str | None
    is_default: bool
    created_at: datetime


class WeeklyProjectExport(BaseSchema):
    id: uuid.UUID
    title: str
    description: str
    difficulty_level: int
    project_path: str
    status: str
    issued_at: datetime
    submitted_at: datetime | None
    metadata_: dict | None = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: datetime


class ProjectTaskExport(BaseSchema):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str
    task_type: str
    order_index: int
    created_at: datetime


class ProjectEvaluationExport(BaseSchema):
    id: uuid.UUID
    project_id: uuid.UUID
    code_quality_score: float
    task_completion: dict
    test_results: dict | None
    overall_assessment: str
    confidence: float
    raw_llm_output: dict | None
    created_at: datetime


class FeedbackExport(BaseSchema):
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    reaction: str | None
    note: str | None
    created_at: datetime


class TriageItemExport(BaseSchema):
    id: uuid.UUID
    source: str
    source_id: uuid.UUID | None
    title: str
    description: str
    context: dict | None
    severity: str
    status: str
    resolution_text: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserSettingsExport(BaseSchema):
    id: uuid.UUID
    key: str
    value: dict
    updated_at: datetime


class OnboardingStateExport(BaseSchema):
    id: uuid.UUID
    completed: bool
    completed_at: datetime | None
    self_assessment: dict | None
    go_experience_level: str | None
    diagnostic_quiz_id: uuid.UUID | None
    topic_interests: dict | None
    created_at: datetime


class ProfileSnapshotExport(BaseSchema):
    id: uuid.UUID
    snapshot_data: dict
    trigger: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Top-level bundle
# ---------------------------------------------------------------------------
class DataExportBundle(BaseModel):
    """Complete application data bundle for device-to-device transfer."""

    format_version: int = Field(
        1, description="Schema version for forward-compatible migrations"
    )
    exported_at: datetime = Field(description="When this export was created")
    app_version: str = Field(description="DevLog+ version that produced the export")

    # Core user data
    journal_entries: list[JournalEntryExport] = []
    journal_entry_versions: list[JournalEntryVersionExport] = []

    # Knowledge profile
    topics: list[TopicExport] = []
    topic_relationships: list[TopicRelationshipExport] = []
    profile_snapshots: list[ProfileSnapshotExport] = []

    # Quizzes
    quiz_sessions: list[QuizSessionExport] = []
    quiz_questions: list[QuizQuestionExport] = []
    quiz_answers: list[QuizAnswerExport] = []
    quiz_evaluations: list[QuizEvaluationExport] = []

    # Readings
    reading_recommendations: list[ReadingRecommendationExport] = []
    reading_allowlist: list[ReadingAllowlistExport] = []

    # Projects
    weekly_projects: list[WeeklyProjectExport] = []
    project_tasks: list[ProjectTaskExport] = []
    project_evaluations: list[ProjectEvaluationExport] = []

    # Signals
    feedback: list[FeedbackExport] = []
    triage_items: list[TriageItemExport] = []

    # Settings & onboarding
    user_settings: list[UserSettingsExport] = []
    onboarding_state: list[OnboardingStateExport] = []


class ImportResult(BaseSchema):
    """Summary returned after a successful import."""

    message: str
    counts: dict[str, int] = Field(
        description="Number of rows imported per table"
    )

class ExportMetadata(BaseSchema):
    """Lightweight metadata returned before downloading the full bundle."""

    format_version: int
    exported_at: datetime
    app_version: str
    table_counts: dict[str, int]
