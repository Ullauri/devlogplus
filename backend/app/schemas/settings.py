"""Settings schemas — re-exported from onboarding for convenience."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.schemas.common import BaseSchema


class SettingUpdate(BaseModel):
    """Set a configuration value."""

    value: dict = Field(
        description="Setting value as a JSON object",
        examples=[{"model": "anthropic/claude-sonnet-4", "temperature": 0.7}],
    )


class SettingResponse(BaseSchema):
    """A single application setting (key-value pair)."""

    id: uuid.UUID = Field(description="Setting ID")
    key: str = Field(description="Unique setting key", examples=["quiz_question_count"])
    value: dict = Field(description="Setting value as a JSON object")
    updated_at: datetime = Field(description="When the setting was last changed")
