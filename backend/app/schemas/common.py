"""Shared schema utilities and base types."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """Base for all response schemas — enables ORM mode."""

    model_config = ConfigDict(from_attributes=True)


class IDTimestampResponse(BaseSchema):
    """Common fields returned on most responses."""

    id: uuid.UUID = Field(description="Unique identifier (UUID v4)")
    created_at: datetime = Field(description="Timestamp when the resource was created")
    updated_at: datetime = Field(description="Timestamp when the resource was last modified")


class IDResponse(BaseSchema):
    """Minimal response with just an ID."""

    id: uuid.UUID = Field(description="Unique identifier (UUID v4)")


class MessageResponse(BaseSchema):
    """Generic message response for operations that return no entity."""

    message: str = Field(description="Human-readable result message", examples=["Entry deleted"])


class PaginationParams(BaseModel):
    """Reusable pagination query parameters."""

    offset: int = Field(0, ge=0, description="Number of records to skip")
    limit: int = Field(50, ge=1, le=200, description="Maximum number of records to return")
