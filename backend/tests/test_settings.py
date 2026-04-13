"""Tests for the settings API endpoints."""

import pytest
from httpx import AsyncClient

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
