"""Tests for the reading recommendations and allowlist API endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
async def test_list_recommendations_empty(client: AsyncClient):
    """Empty list when no recommendations exist."""
    resp = await client.get("/api/v1/readings/recommendations")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Allowlist CRUD
# ---------------------------------------------------------------------------
async def test_list_allowlist_empty(client: AsyncClient):
    """Empty allowlist when nothing is seeded."""
    resp = await client.get("/api/v1/readings/allowlist")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_add_allowlist_entry(client: AsyncClient):
    """Add a new domain to the allowlist."""
    resp = await client.post(
        "/api/v1/readings/allowlist",
        json={
            "domain": "example.com",
            "name": "Example Site",
            "description": "A test domain",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["domain"] == "example.com"
    assert data["name"] == "Example Site"
    assert data["is_default"] is False


async def test_update_allowlist_entry(client: AsyncClient):
    """Update an existing allowlist entry."""
    create_resp = await client.post(
        "/api/v1/readings/allowlist",
        json={"domain": "update-test.com", "name": "Original"},
    )
    entry_id = create_resp.json()["id"]

    update_resp = await client.put(
        f"/api/v1/readings/allowlist/{entry_id}",
        json={"name": "Updated Name", "description": "Now with description"},
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Now with description"


async def test_update_nonexistent_allowlist(client: AsyncClient):
    """Updating a nonexistent entry returns 404."""
    resp = await client.put(
        "/api/v1/readings/allowlist/00000000-0000-0000-0000-000000000000",
        json={"name": "nope"},
    )
    assert resp.status_code == 404


async def test_delete_allowlist_entry(client: AsyncClient):
    """Delete an allowlist entry."""
    create_resp = await client.post(
        "/api/v1/readings/allowlist",
        json={"domain": "delete-me.com", "name": "Deletable"},
    )
    entry_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/readings/allowlist/{entry_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["message"] == "Allowlist entry deleted"


async def test_delete_nonexistent_allowlist(client: AsyncClient):
    """Deleting a nonexistent entry returns 404."""
    resp = await client.delete("/api/v1/readings/allowlist/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
