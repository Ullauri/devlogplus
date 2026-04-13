"""Feedback schemas — feedback + feedforward on generated items."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.models.base import FeedbackReaction, FeedbackTargetType
from backend.app.schemas.common import BaseSchema


class FeedbackCreate(BaseModel):
    """Submit feedback and/or feedforward on a generated item.

    At least one of `reaction` or `note` should be provided.
    """

    target_type: FeedbackTargetType = Field(
        description="Type of item receiving feedback: quiz_question, reading, or project"
    )
    target_id: uuid.UUID = Field(
        description="ID of the target item (question, reading, or project)"
    )
    reaction: FeedbackReaction | None = Field(
        None,
        description="Quick reaction: thumbs_up or thumbs_down (feedback signal)",
    )
    note: str | None = Field(
        None,
        description=(
            "Free-text feedforward note that shapes future generation "
            "(e.g. 'more backend-oriented content', 'harder debugging tasks')"
        ),
        examples=["This was too easy — I'd prefer more advanced concurrency challenges."],
    )


class FeedbackResponse(BaseSchema):
    """A recorded feedback/feedforward entry."""

    id: uuid.UUID = Field(description="Feedback entry ID")
    target_type: FeedbackTargetType = Field(description="Type of item this feedback targets")
    target_id: uuid.UUID = Field(description="ID of the targeted item")
    reaction: FeedbackReaction | None = Field(
        description="Thumbs-up / thumbs-down reaction, if provided"
    )
    note: str | None = Field(description="Free-text feedforward note, if provided")
    created_at: datetime = Field(description="When the feedback was submitted")
