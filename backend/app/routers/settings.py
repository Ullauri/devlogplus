"""Settings API — user-configurable application settings."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.schemas.settings import SettingResponse, SettingUpdate
from backend.app.services import onboarding as onboarding_svc

router = APIRouter(prefix="/settings", tags=["settings"])

# ---------------------------------------------------------------------------
# Reserved keys — these belong in .env and must NOT be overridable through the
# API. Keeping credentials / model selection out of the database is a
# defense-in-depth measure against:
#   * an attacker with write access to the DB redirecting LLM traffic to a
#     malicious OpenRouter proxy,
#   * accidental leaks via the /transfer export bundle,
#   * operator confusion about where the source of truth lives.
# The frontend enforces the same list for UX, but this is the authoritative
# check.
# ---------------------------------------------------------------------------
RESERVED_KEY_PREFIXES: tuple[str, ...] = (
    "llm_model_",
    "openrouter_",
    "langfuse_",
)
RESERVED_KEYS: frozenset[str] = frozenset(
    {
        "database_url",
        "app_env",
        "log_level",
        "workspace_projects_dir",
        "frontend_dist_dir",
    }
)


def _is_reserved_key(key: str) -> bool:
    """Return True if the setting key must only come from environment variables."""
    if key in RESERVED_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in RESERVED_KEY_PREFIXES)


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
    responses={
        403: {
            "description": (
                "Key is reserved for environment variables (e.g. LLM model "
                "selection, API credentials) and cannot be set through the API."
            )
        }
    },
)
async def set_setting(
    key: str,
    data: SettingUpdate,
    db: AsyncSession = Depends(get_db),
) -> SettingResponse:
    """Create a new setting or update an existing one.

    The `value` field accepts any JSON object.  If the key already exists,
    its value is replaced.

    Keys that control LLM model selection or credentials (``llm_model_*``,
    ``openrouter_*``, ``langfuse_*``, ``database_url``, …) are reserved for
    the ``.env`` configuration and will be rejected with 403 — this prevents
    the database (and export bundles) from becoming a surface for altering
    security-sensitive configuration.
    """
    if _is_reserved_key(key):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Setting '{key}' is reserved for environment variables "
                "and cannot be modified via the API. Update your .env file instead."
            ),
        )
    setting = await onboarding_svc.set_setting(db, key, data.value)
    return SettingResponse.model_validate(setting)
