"""Shared schema utilities and base types."""

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


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


class PaginatedResponse(BaseModel, Generic[T]):
    """Envelope returned by list endpoints that support offset/limit pagination.

    AI-agent clients (and any other API consumer) use the envelope's ``total``,
    ``offset`` and ``limit`` fields to know how many more pages to fetch
    without issuing a speculative trailing request. ``items`` holds the rows
    for the current page.
    """

    items: list[T] = Field(description="Rows returned for the current page.")
    total: int = Field(
        ge=0,
        description="Total number of rows that match the query, across all pages.",
    )
    offset: int = Field(
        ge=0,
        description="Offset used for this page (echo of the request parameter).",
    )
    limit: int = Field(
        ge=1,
        description="Page size used for this page (echo of the request parameter).",
    )
