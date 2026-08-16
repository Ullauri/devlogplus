"""Onboarding service — first-run experience and settings management."""

import logging
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.settings import OnboardingState, UserSettings
from backend.app.schemas.onboarding import OnboardingCompleteRequest

logger = logging.getLogger(__name__)


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


def _unwrap_scalar(value: object) -> object:
    """Unwrap the ``{"value": x}`` envelope the Settings page writes.

    ``SettingUpdate.value`` is a JSON object, so a scalar setting reaches the
    database wrapped. Bare scalars are accepted too — the /transfer import path
    writes whatever the bundle contains, and it need not have come from the UI.
    """
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


async def get_int_setting(
    db: AsyncSession,
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    """Resolve an integer tunable, preferring the user's saved value.

    Returns the value stored under *key* in ``user_settings`` when there is one
    and it is a whole number within ``[minimum, maximum]``; otherwise *default*.

    *default* is passed in rather than read from ``config``: this layer must not
    import it (services depend on models and schemas only), and keeping the
    fallback at the call site is what lets the caller decide which env setting
    backs which key.

    A stored value that is unusable is logged at WARNING and ignored. It is
    never repaired or deleted — the row is the user's, and silently rewriting it
    would hide the disagreement rather than surface it.
    """
    setting = await get_setting(db, key)
    if setting is None:
        return default

    raw = _unwrap_scalar(setting.value)
    # bool is a subclass of int; `True` is not a question count.
    if isinstance(raw, bool) or not isinstance(raw, int):
        logger.warning(
            "Setting %r is not a whole number (%r); falling back to %d.",
            key,
            setting.value,
            default,
        )
        return default

    if not minimum <= raw <= maximum:
        logger.warning(
            "Setting %r is %d, outside the allowed range %d-%d; falling back to %d.",
            key,
            raw,
            minimum,
            maximum,
            default,
        )
        return default

    return raw
