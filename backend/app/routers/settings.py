"""Settings API — user-configurable application settings."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.schemas.settings import SettingResponse, SettingUpdate
from backend.app.services import onboarding as onboarding_svc

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "",
    response_model=list[SettingResponse],
    summary="List all settings",
    response_description="All stored application settings",
)
async def list_settings(
    db: AsyncSession = Depends(get_db),
) -> list[SettingResponse]:
    """Return every application setting as a key-value pair.

    Settings include model selection, quiz question count, cron schedules,
    and other tunables.  Values are stored as JSON objects.
    """
    settings = await onboarding_svc.list_settings(db)
    return [SettingResponse.model_validate(s) for s in settings]


@router.get(
    "/{key}",
    response_model=SettingResponse,
    summary="Get a setting by key",
    response_description="The requested setting",
    responses={404: {"description": "Setting not found"}},
)
async def get_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
) -> SettingResponse:
    """Retrieve a single setting by its unique key."""
    setting = await onboarding_svc.get_setting(db, key)
    if setting is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return SettingResponse.model_validate(setting)


@router.put(
    "/{key}",
    response_model=SettingResponse,
    summary="Create or update a setting",
    response_description="The created or updated setting",
)
async def set_setting(
    key: str,
    data: SettingUpdate,
    db: AsyncSession = Depends(get_db),
) -> SettingResponse:
    """Create a new setting or update an existing one.

    The `value` field accepts any JSON object.  If the key already exists,
    its value is replaced.
    """
    setting = await onboarding_svc.set_setting(db, key, data.value)
    return SettingResponse.model_validate(setting)
