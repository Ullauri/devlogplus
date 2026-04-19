"""Reading recommendations and allowlist API."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.schemas.common import MessageResponse, PaginatedResponse
from backend.app.schemas.reading import (
    AllowlistEntryCreate,
    AllowlistEntryResponse,
    AllowlistEntryUpdate,
    ReadingRecommendationResponse,
)
from backend.app.services import reading as reading_svc

router = APIRouter(prefix="/readings", tags=["readings"])


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
@router.get(
    "/recommendations",
    response_model=PaginatedResponse[ReadingRecommendationResponse],
    summary="List reading recommendations",
    response_description=("Paginated envelope of reading recommendations, most recent batch first"),
)
async def list_recommendations(
    offset: int = Query(0, ge=0, description="Number of recommendations to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum recommendations to return"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ReadingRecommendationResponse]:
    """Return reading recommendations ordered by batch date (most recent first).

    Recommendations are generated weekly from the Knowledge Profile and limited
    to domains on the user's allowlist.  Each batch typically contains 3–5 links.
    The response is wrapped in a :class:`PaginatedResponse` envelope so agent
    clients know the full size of the archive in a single request.
    """
    recs = await reading_svc.list_recommendations(db, offset=offset, limit=limit)
    total = await reading_svc.count_recommendations(db)
    return PaginatedResponse[ReadingRecommendationResponse](
        items=[ReadingRecommendationResponse.model_validate(r) for r in recs],
        total=total,
        offset=offset,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------
@router.get(
    "/allowlist",
    response_model=list[AllowlistEntryResponse],
    summary="List allowlisted domains",
    response_description="All domains currently on the reading allowlist",
)
async def list_allowlist(
    db: AsyncSession = Depends(get_db),
) -> list[AllowlistEntryResponse]:
    """Return every domain on the reading allowlist.

    The allowlist controls which domains the reading-generation pipeline may
    link to.  Default entries are pre-populated on first run.
    """
    entries = await reading_svc.list_allowlist(db)
    return [AllowlistEntryResponse.model_validate(e) for e in entries]


@router.post(
    "/allowlist",
    response_model=AllowlistEntryResponse,
    status_code=201,
    summary="Add allowlist domain",
    response_description="The newly created allowlist entry",
    responses={422: {"description": "Validation error — domain and name are required"}},
)
async def add_allowlist_entry(
    data: AllowlistEntryCreate,
    db: AsyncSession = Depends(get_db),
) -> AllowlistEntryResponse:
    """Add a new domain to the reading allowlist.

    Once added, the reading-generation pipeline may include links from this
    domain in future weekly recommendations.
    """
    entry = await reading_svc.add_allowlist_entry(db, data)
    return AllowlistEntryResponse.model_validate(entry)


@router.put(
    "/allowlist/{entry_id}",
    response_model=AllowlistEntryResponse,
    summary="Update allowlist entry",
    response_description="The updated allowlist entry",
    responses={404: {"description": "Allowlist entry not found"}},
)
async def update_allowlist_entry(
    entry_id: uuid.UUID,
    data: AllowlistEntryUpdate,
    db: AsyncSession = Depends(get_db),
) -> AllowlistEntryResponse:
    """Update the name or description of an existing allowlist entry."""
    entry = await reading_svc.update_allowlist_entry(db, entry_id, data)
    if entry is None:
        raise HTTPException(status_code=404, detail="Allowlist entry not found")
    return AllowlistEntryResponse.model_validate(entry)


@router.delete(
    "/allowlist/{entry_id}",
    response_model=MessageResponse,
    summary="Remove allowlist domain",
    response_description="Confirmation message",
    responses={404: {"description": "Allowlist entry not found"}},
)
async def delete_allowlist_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Remove a domain from the reading allowlist.

    Future reading recommendations will no longer include links from this
    domain.  Existing recommendations are not affected.
    """
    deleted = await reading_svc.delete_allowlist_entry(db, entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Allowlist entry not found")
    return MessageResponse(message="Allowlist entry deleted")
