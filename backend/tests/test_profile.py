"""Tests for the profile API endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_get_empty_profile(client: AsyncClient):
    """An empty profile returns the correct structure with zero topics."""
    resp = await client.get("/api/v1/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_topics"] == 0
    assert data["strengths"] == []
    assert data["weak_spots"] == []
    assert data["current_frontier"] == []
    assert data["next_frontier"] == []
    assert data["recurring_themes"] == []
    assert data["unresolved"] == []


async def test_list_snapshots_empty(client: AsyncClient):
    """Empty snapshot list when no snapshots exist."""
    resp = await client.get("/api/v1/profile/snapshots")
    assert resp.status_code == 200
    assert resp.json() == []
