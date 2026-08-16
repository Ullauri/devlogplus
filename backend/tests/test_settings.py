"""Tests for the settings API endpoints and the DB-setting resolver."""

import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.settings import UserSettings
from backend.app.services import onboarding as onboarding_svc

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_list_settings_empty(client: AsyncClient):
    """Listing settings when none exist returns an empty list."""
    resp = await client.get("/api/v1/settings")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_set_and_get_setting(client: AsyncClient):
    """Create a setting, then retrieve it by key."""
    # Create
    put_resp = await client.put(
        "/api/v1/settings/quiz_count",
        json={"value": {"count": 15}},
    )
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["key"] == "quiz_count"
    assert data["value"] == {"count": 15}

    # Get
    get_resp = await client.get("/api/v1/settings/quiz_count")
    assert get_resp.status_code == 200
    assert get_resp.json()["value"] == {"count": 15}


async def test_update_existing_setting(client: AsyncClient):
    """Updating a setting overwrites its value."""
    await client.put("/api/v1/settings/theme", json={"value": {"mode": "dark"}})
    resp = await client.put("/api/v1/settings/theme", json={"value": {"mode": "light"}})
    assert resp.status_code == 200
    assert resp.json()["value"] == {"mode": "light"}


async def test_get_nonexistent_setting(client: AsyncClient):
    """Getting a nonexistent key returns 404."""
    resp = await client.get("/api/v1/settings/does_not_exist")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "reserved_key",
    [
        "llm_model_quiz_generation",
        "openrouter_api_key",
        "langfuse_public_key",
        "database_url",
        "app_env",
        "log_level",
    ],
)
async def test_reserved_keys_cannot_be_set(client: AsyncClient, reserved_key: str):
    """Keys that belong in .env must be rejected with 403 by PUT /settings/{key}.

    This is a defense-in-depth check: the frontend guards the same list for
    UX, but the API is the authoritative enforcement point (protects against
    direct curl calls, misbehaving clients, and malicious import bundles
    being replayed through the API).
    """
    resp = await client.put(
        f"/api/v1/settings/{reserved_key}",
        json={"value": {"anything": "here"}},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert reserved_key in body["detail"]
    assert ".env" in body["detail"]

    # And it must not have been persisted.
    get_resp = await client.get(f"/api/v1/settings/{reserved_key}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# get_int_setting — the seam between "user saved a value" and "a pipeline used
# it". Regression: the Settings page wrote quiz_question_count to the database
# and both pipelines read the .env value, so saving the slider did nothing at
# all. Nothing tested the join, which is why it survived.
# ---------------------------------------------------------------------------


class TestGetIntSetting:
    async def test_missing_key_falls_back_to_default(self, db_session: AsyncSession):
        value = await onboarding_svc.get_int_setting(
            db_session, "quiz_question_count", 10, minimum=1, maximum=50
        )
        assert value == 10

    async def test_stored_value_wins_over_default(self, db_session: AsyncSession):
        """The whole point: a saved setting must beat the .env default."""
        await onboarding_svc.set_setting(db_session, "quiz_question_count", {"value": 5})

        value = await onboarding_svc.get_int_setting(
            db_session, "quiz_question_count", 10, minimum=1, maximum=50
        )
        assert value == 5

    async def test_bare_scalar_is_accepted(self, db_session: AsyncSession):
        """Import bundles need not use the UI's {"value": x} envelope.

        Written through the model rather than ``set_setting`` because the API
        schema types the column as an object; only /transfer can land a bare
        scalar here.
        """
        db_session.add(UserSettings(key="quiz_question_count", value=7))
        await db_session.flush()

        value = await onboarding_svc.get_int_setting(
            db_session, "quiz_question_count", 10, minimum=1, maximum=50
        )
        assert value == 7

    async def test_boundaries_are_inclusive(self, db_session: AsyncSession):
        await onboarding_svc.set_setting(db_session, "quiz_question_count", {"value": 50})
        assert (
            await onboarding_svc.get_int_setting(
                db_session, "quiz_question_count", 10, minimum=1, maximum=50
            )
            == 50
        )

    @pytest.mark.parametrize(
        ("stored", "reason"),
        [
            ({"value": 0}, "below minimum"),
            ({"value": 51}, "above maximum"),
            ({"value": "12"}, "a string, not a number"),
            ({"value": 12.5}, "not a whole number"),
            ({"value": True}, "a bool — int subclass, but not a count"),
            ({"value": None}, "explicitly null"),
            ({"count": 12}, "wrong envelope key"),
        ],
        ids=["too_small", "too_big", "string", "float", "bool", "null", "wrong_key"],
    )
    async def test_unusable_value_falls_back(
        self, db_session: AsyncSession, stored: dict, reason: str
    ):
        await onboarding_svc.set_setting(db_session, "quiz_question_count", stored)

        value = await onboarding_svc.get_int_setting(
            db_session, "quiz_question_count", 10, minimum=1, maximum=50
        )
        assert value == 10, f"expected fallback because value is {reason}"

    async def test_unusable_value_is_logged_not_silent(
        self, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
    ):
        """Falling back must leave a trace — a silent fallback is the same
        class of bug as the one this resolver exists to fix."""
        await onboarding_svc.set_setting(db_session, "quiz_question_count", {"value": 999})

        with caplog.at_level(logging.WARNING, logger=onboarding_svc.__name__):
            await onboarding_svc.get_int_setting(
                db_session, "quiz_question_count", 10, minimum=1, maximum=50
            )

        assert any("quiz_question_count" in r.getMessage() for r in caplog.records)

    async def test_out_of_range_row_is_left_alone(self, db_session: AsyncSession):
        """The resolver reads; it does not repair the user's row."""
        await onboarding_svc.set_setting(db_session, "quiz_question_count", {"value": 999})

        await onboarding_svc.get_int_setting(
            db_session, "quiz_question_count", 10, minimum=1, maximum=50
        )

        setting = await onboarding_svc.get_setting(db_session, "quiz_question_count")
        assert setting is not None
        assert setting.value == {"value": 999}
