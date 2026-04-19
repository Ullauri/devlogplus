"""Tests for the journal API endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
async def test_create_journal_entry(client: AsyncClient):
    """Creating a journal entry should return 201 with the entry data."""
    response = await client.post(
        "/api/v1/journal/entries",
        json={"title": "Test Entry", "content": "Learned about Go interfaces today."},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Entry"
    assert data["current_content"] == "Learned about Go interfaces today."
    assert data["is_processed"] is False


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------
async def test_list_journal_entries(client: AsyncClient):
    """Listing entries should return a paginated envelope."""
    response = await client.get("/api/v1/journal/entries")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert isinstance(body["items"], list)
    assert "total" in body
    assert body["offset"] == 0
    assert body["limit"] == 50


# ---------------------------------------------------------------------------
# Get (not found / found)
# ---------------------------------------------------------------------------
async def test_get_nonexistent_entry(client: AsyncClient):
    """Getting a nonexistent entry should return 404."""
    response = await client.get("/api/v1/journal/entries/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_get_entry_detail(client: AsyncClient):
    """Getting an entry by ID returns full detail with versions."""
    create = await client.post(
        "/api/v1/journal/entries",
        json={"title": "Detail Test", "content": "Detail content"},
    )
    entry_id = create.json()["id"]
    response = await client.get(f"/api/v1/journal/entries/{entry_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Detail Test"
    assert len(data["versions"]) == 1
    assert data["versions"][0]["is_current"] is True


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
async def test_update_journal_entry(client: AsyncClient):
    """Editing a journal entry creates a new version and updates the title."""
    create = await client.post(
        "/api/v1/journal/entries",
        json={"title": "Original", "content": "v1 content"},
    )
    entry_id = create.json()["id"]

    update_resp = await client.put(
        f"/api/v1/journal/entries/{entry_id}",
        json={"title": "Updated Title", "content": "v2 content"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "Updated Title"
    assert update_resp.json()["current_content"] == "v2 content"

    # Verify version history
    detail = await client.get(f"/api/v1/journal/entries/{entry_id}")
    assert len(detail.json()["versions"]) == 2


async def test_update_nonexistent_entry(client: AsyncClient):
    """Updating a nonexistent entry returns 404."""
    resp = await client.put(
        "/api/v1/journal/entries/00000000-0000-0000-0000-000000000000",
        json={"content": "nope"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
async def test_delete_journal_entry(client: AsyncClient):
    """Deleting a journal entry removes it."""
    create = await client.post(
        "/api/v1/journal/entries",
        json={"title": "To Delete", "content": "bye"},
    )
    entry_id = create.json()["id"]

    del_resp = await client.delete(f"/api/v1/journal/entries/{entry_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["message"] == "Entry deleted"

    # Verify it's gone
    get_resp = await client.get(f"/api/v1/journal/entries/{entry_id}")
    assert get_resp.status_code == 404


async def test_delete_nonexistent_entry(client: AsyncClient):
    """Deleting a nonexistent entry returns 404."""
    resp = await client.delete("/api/v1/journal/entries/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
