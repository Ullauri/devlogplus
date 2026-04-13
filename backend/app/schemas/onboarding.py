"""Settings and onboarding schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.schemas.common import BaseSchema


# ---------------------------------------------------------------------------
# User Settings
# ---------------------------------------------------------------------------
class SettingUpdate(BaseModel):
    """Set a configuration value."""

    value: dict = Field(description="Setting value as a JSON object")


class SettingResponse(BaseSchema):
    """A single application setting."""

    id: uuid.UUID = Field(description="Setting ID")
    key: str = Field(description="Unique setting key")
    value: dict = Field(description="Setting value as a JSON object")
    updated_at: datetime = Field(description="When the setting was last changed")


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------
class OnboardingSelfAssessment(BaseModel):
    """First-run self-assessment of technical background."""

    primary_languages: list[str] = Field(
        default=[],
        description="Programming languages the user is most comfortable with",
        examples=[["Python", "Go", "TypeScript"]],
    )
    years_experience: int | None = Field(
        None, description="Total years of professional development experience", ge=0
    )
    primary_domain: str | None = Field(
        None,
        description="Primary work domain",
        examples=["backend", "full-stack", "devops", "data-engineering"],
    )
    comfort_areas: list[str] = Field(
        default=[],
        description="Technical areas the user feels confident in",
        examples=[["REST APIs", "SQL databases", "Docker"]],
    )
    growth_areas: list[str] = Field(
        default=[],
        description="Technical areas the user wants to improve",
        examples=[["distributed systems", "Go concurrency", "performance tuning"]],
    )


class OnboardingGoExperience(BaseModel):
    """Go-specific experience level for project difficulty calibration."""

    level: str = Field(
        description="Self-reported Go experience level",
        examples=["none", "beginner", "intermediate", "advanced"],
    )
    details: str | None = Field(
        None,
        description="Optional free-text elaboration on Go experience",
        examples=["Built a few CLI tools and a small HTTP server."],
    )


class OnboardingCompleteRequest(BaseModel):
    """Complete the first-run onboarding flow (~10–15 min)."""

    self_assessment: OnboardingSelfAssessment = Field(
        description="Technical background self-assessment"
    )
    go_experience: OnboardingGoExperience = Field(
        description="Go-specific experience level and optional details"
    )
    topic_interests: list[str] | None = Field(
        None,
        description="Optional list of topics the user wants to prioritise",
        examples=[["concurrency", "testing", "microservices"]],
    )


class OnboardingStateResponse(BaseSchema):
    """Current state of the onboarding flow."""

    id: uuid.UUID | None = Field(None, description="Onboarding record ID")
    completed: bool = Field(description="Whether onboarding has been completed")
    completed_at: datetime | None = Field(None, description="When onboarding was completed")
    self_assessment: dict | None = Field(
        None, description="Serialised self-assessment answers (JSONB)"
    )
    go_experience_level: str | None = Field(None, description="Go experience level string")
    topic_interests: dict | None = Field(None, description="Serialised topic interest list (JSONB)")
    created_at: datetime | None = Field(None, description="Record creation timestamp")
