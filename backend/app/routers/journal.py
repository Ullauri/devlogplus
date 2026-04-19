"""Journal API — CRUD for technical journal entries."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.schemas.common import MessageResponse, PaginatedResponse
from backend.app.schemas.journal import (
    JournalEntryCreate,
    JournalEntryDetailResponse,
    JournalEntryResponse,
    JournalEntryUpdate,
    JournalEntryVersionResponse,
)
from backend.app.services import journal as journal_svc

router = APIRouter(prefix="/journal", tags=["journal"])


@router.post(
    "/entries",
    response_model=JournalEntryResponse,
    status_code=201,
    summary="Create journal entry",
    response_description="The newly created journal entry",
    responses={
        422: {"description": "Validation error — content is required and must be non-empty"}
    },
)
async def create_entry(
    data: JournalEntryCreate,
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    """Create a new technical journal entry.

    The entry content can be typed text or dictated via the browser Web Speech
    API.  An initial version is created automatically.  The entry will be
    processed by the nightly profile-update pipeline.
    """
    entry = await journal_svc.create_entry(db, data)
    return journal_svc.entry_to_response(entry)


@router.get(
    "/entries",
    response_model=PaginatedResponse[JournalEntryResponse],
    summary="List journal entries",
    response_description="Paginated envelope of journal entries, most recent first",
)
async def list_entries(
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    limit: int = Query(50, ge=1, le=200, description="Maximum entries to return"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[JournalEntryResponse]:
    """Return journal entries ordered by creation date (most recent first).

    Supports offset/limit pagination. Response is wrapped in a
    :class:`PaginatedResponse` so clients (notably AI agents) can tell when
    they've reached the last page without an extra speculative request.
    Each entry includes its latest content snapshot.
    """
    entries = await journal_svc.list_entries(db, offset=offset, limit=limit)
    total = await journal_svc.count_entries(db)
    return PaginatedResponse[JournalEntryResponse](
        items=[journal_svc.entry_to_response(e) for e in entries],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/entries/{entry_id}",
    response_model=JournalEntryDetailResponse,
    summary="Get journal entry with version history",
    response_description="The journal entry with all historical versions",
    responses={404: {"description": "Journal entry not found"}},
)
async def get_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JournalEntryDetailResponse:
    """Retrieve a single journal entry including its full version history.

    Versions are append-only; the most recent version is the source of truth.
    """
    entry = await journal_svc.get_entry(db, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    resp = journal_svc.entry_to_response(entry)
    return JournalEntryDetailResponse(
        **resp.model_dump(),
        versions=[JournalEntryVersionResponse.model_validate(v) for v in entry.versions],
    )


@router.put(
    "/entries/{entry_id}",
    response_model=JournalEntryResponse,
    summary="Edit journal entry",
    response_description="The updated journal entry (new version created)",
    responses={404: {"description": "Journal entry not found"}},
)
async def update_entry(
    entry_id: uuid.UUID,
    data: JournalEntryUpdate,
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    """Edit a journal entry.

    Creates a new version instead of overwriting — the previous content is
    preserved in the version history.  The new version becomes the source of
    truth for future profile updates.
    """
    entry = await journal_svc.update_entry(db, entry_id, data)
    if entry is None:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return journal_svc.entry_to_response(entry)


@router.delete(
    "/entries/{entry_id}",
    response_model=MessageResponse,
    summary="Delete journal entry",
    response_description="Confirmation message",
    responses={404: {"description": "Journal entry not found"}},
)
async def delete_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Permanently delete a journal entry and all of its versions."""
    deleted = await journal_svc.delete_entry(db, entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return MessageResponse(message="Entry deleted")
