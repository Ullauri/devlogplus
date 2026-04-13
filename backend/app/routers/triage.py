"""Triage API — manage items requiring user attention."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models.base import TriageSeverity, TriageStatus
from backend.app.schemas.triage import TriageItemResponse, TriageResolveRequest
from backend.app.services import triage as triage_svc

router = APIRouter(prefix="/triage", tags=["triage"])


@router.get(
    "",
    response_model=list[TriageItemResponse],
    summary="List triage items",
    response_description="Paginated list of triage items matching the optional filters",
)
async def list_triage_items(
    status: TriageStatus | None = Query(
        None, description="Filter by status (pending, accepted, rejected, edited, deferred)"
    ),
    severity: TriageSeverity | None = Query(
        None, description="Filter by severity (low, medium, high, critical)"
    ),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(50, ge=1, le=200, description="Maximum items to return"),
    db: AsyncSession = Depends(get_db),
) -> list[TriageItemResponse]:
    """Return triage items with optional status and severity filters.

    Triage items are created automatically by the profile-update,
    quiz-evaluation, and project-evaluation pipelines when the system
    encounters ambiguity it cannot resolve on its own.
    """
    items = await triage_svc.list_triage_items(
        db, status=status, severity=severity, offset=offset, limit=limit
    )
    return [TriageItemResponse.model_validate(i) for i in items]


@router.get(
    "/blocking",
    response_model=dict,
    summary="Check for blocking triage items",
    response_description="Object with a single boolean field `blocking`",
)
async def check_blocking_triage(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Check whether unresolved high or critical triage items exist.

    When blocking items are present, the nightly profile-update pipeline
    will not run until they are resolved.  The frontend should surface a
    prominent warning in this case.
    """
    blocking = await triage_svc.has_blocking_triage(db)
    return {"blocking": blocking}


@router.get(
    "/{item_id}",
    response_model=TriageItemResponse,
    summary="Get triage item",
    response_description="A single triage item with full details",
    responses={404: {"description": "Triage item not found"}},
)
async def get_triage_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TriageItemResponse:
    """Retrieve a specific triage item by ID."""
    item = await triage_svc.get_triage_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Triage item not found")
    return TriageItemResponse.model_validate(item)


@router.post(
    "/{item_id}/resolve",
    response_model=TriageItemResponse,
    summary="Resolve triage item",
    response_description="The resolved triage item",
    responses={404: {"description": "Triage item not found"}},
)
async def resolve_triage_item(
    item_id: uuid.UUID,
    data: TriageResolveRequest,
    db: AsyncSession = Depends(get_db),
) -> TriageItemResponse:
    """Resolve a triage item with a user action and optional clarification.

    Allowed actions: `accepted`, `rejected`, `edited`, `deferred`.  When the
    action is `edited`, `resolution_text` should contain the user's
    clarifying input.
    """
    item = await triage_svc.resolve_triage_item(db, item_id, data)
    if item is None:
        raise HTTPException(status_code=404, detail="Triage item not found")
    return TriageItemResponse.model_validate(item)
