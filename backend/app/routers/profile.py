"""Knowledge Profile API — read-only view of the AI-derived profile."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.schemas.topic import (
    KnowledgeProfileResponse,
    ProfileSnapshotResponse,
)
from backend.app.services import profile as profile_svc

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get(
    "",
    response_model=KnowledgeProfileResponse,
    summary="Get Knowledge Profile",
    response_description="The full Knowledge Profile organized by evidence strength",
)
async def get_profile(
    db: AsyncSession = Depends(get_db),
) -> KnowledgeProfileResponse:
    """Return the current Knowledge Profile.

    The profile is an AI-derived, read-only view of the user's technical
    knowledge.  Topics are organized into:

    - **strengths** — topics with strong evidence
    - **weak_spots** — topics with limited evidence
    - **current_frontier** — topics actively being learned
    - **next_frontier** — adjacent topics recommended for exploration
    - **recurring_themes** — frequently mentioned topics
    - **unresolved** — topics pending triage

    Updated nightly by the profile-update pipeline.
    """
    return await profile_svc.get_knowledge_profile(db)


@router.get(
    "/snapshots",
    response_model=list[ProfileSnapshotResponse],
    summary="List profile snapshots",
    response_description="Paginated list of historical profile snapshots",
)
async def list_snapshots(
    offset: int = Query(0, ge=0, description="Number of snapshots to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum snapshots to return"),
    db: AsyncSession = Depends(get_db),
) -> list[ProfileSnapshotResponse]:
    """List historical profile snapshots in reverse-chronological order.

    Each snapshot captures the full Knowledge Profile state at a point in time,
    enabling the user to track knowledge growth over weeks and months.
    """
    snapshots = await profile_svc.list_snapshots(db, offset=offset, limit=limit)
    return [ProfileSnapshotResponse.model_validate(s) for s in snapshots]
