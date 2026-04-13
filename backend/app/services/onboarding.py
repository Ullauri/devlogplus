"""Onboarding service — first-run experience and settings management."""

from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.settings import OnboardingState, UserSettings
from backend.app.schemas.onboarding import OnboardingCompleteRequest


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------
async def get_onboarding_state(db: AsyncSession) -> OnboardingState | None:
    """Get the current onboarding state (there should be at most one)."""
    stmt = select(OnboardingState).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def is_onboarding_complete(db: AsyncSession) -> bool:
    """Check whether onboarding has been completed."""
    state = await get_onboarding_state(db)
    return state is not None and state.completed


async def complete_onboarding(db: AsyncSession, data: OnboardingCompleteRequest) -> OnboardingState:
    """Complete the onboarding flow and store baseline context."""
    from datetime import datetime

    state = await get_onboarding_state(db)
    if state is None:
        state = OnboardingState()
        db.add(state)

    state.completed = True
    state.completed_at = datetime.now(UTC)
    state.self_assessment = data.self_assessment.model_dump()
    state.go_experience_level = data.go_experience.level
    state.topic_interests = {"topics": data.topic_interests} if data.topic_interests else None

    await db.flush()
    return state


# ---------------------------------------------------------------------------
# User settings
# ---------------------------------------------------------------------------
async def get_setting(db: AsyncSession, key: str) -> UserSettings | None:
    """Get a single setting by key."""
    stmt = select(UserSettings).where(UserSettings.key == key)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def set_setting(db: AsyncSession, key: str, value: dict) -> UserSettings:
    """Create or update a setting."""
    setting = await get_setting(db, key)
    if setting is None:
        setting = UserSettings(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
    await db.flush()
    await db.refresh(setting)
    return setting


async def list_settings(db: AsyncSession) -> list[UserSettings]:
    """List all user settings."""
    stmt = select(UserSettings).order_by(UserSettings.key)
    result = await db.execute(stmt)
    return list(result.scalars().all())
