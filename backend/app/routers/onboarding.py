"""Onboarding API — first-run experience."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.schemas.onboarding import (
    OnboardingCompleteRequest,
    OnboardingStateResponse,
)
from backend.app.services import onboarding as onboarding_svc

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get(
    "/status",
    response_model=dict,
    summary="Check onboarding status",
    response_description="Object with a single boolean field `completed`",
)
async def get_onboarding_status(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Check whether the first-run onboarding has been completed.

    Returns `{"completed": true}` after the onboarding flow finishes.
    The frontend should redirect to the onboarding wizard when `false`.
    """
    completed = await onboarding_svc.is_onboarding_complete(db)
    return {"completed": completed}


@router.get(
    "/state",
    response_model=OnboardingStateResponse,
    summary="Get onboarding state",
    response_description="Full onboarding state including self-assessment data",
)
async def get_onboarding_state(
    db: AsyncSession = Depends(get_db),
) -> OnboardingStateResponse:
    """Retrieve the full onboarding state.

    Returns the self-assessment answers, Go experience level, topic interests,
    and completion timestamp.  Returns empty/default values if onboarding
    has not started.
    """
    state = await onboarding_svc.get_onboarding_state(db)
    if state is None:
        return OnboardingStateResponse(
            completed=False,
            completed_at=None,
            self_assessment=None,
            go_experience_level=None,
            topic_interests=None,
        )
    return OnboardingStateResponse.model_validate(state)


@router.post(
    "/complete",
    response_model=OnboardingStateResponse,
    summary="Complete onboarding",
    response_description="The completed onboarding state",
    responses={
        422: {"description": "Validation error — self_assessment and go_experience required"}
    },
)
async def complete_onboarding(
    data: OnboardingCompleteRequest,
    db: AsyncSession = Depends(get_db),
) -> OnboardingStateResponse:
    """Complete the first-run onboarding flow (~10–15 min).

    Collects:
    - **Self-assessment** — technical background, languages, experience
    - **Go experience level** — none / beginner / intermediate / advanced
    - **Topic interests** — optional list of topics to prioritise

    This establishes baseline context before the normal nightly/weekly
    processing cycles begin.
    """
    state = await onboarding_svc.complete_onboarding(db, data)
    return OnboardingStateResponse.model_validate(state)
