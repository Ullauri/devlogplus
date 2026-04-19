"""Tests for the feedback API endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_create_feedback_thumbs_up(client: AsyncClient):
    """Submit thumbs-up feedback on a quiz question."""
    resp = await client.post(
        "/api/v1/feedback",
        json={
            "target_type": "quiz_question",
            "target_id": "00000000-0000-0000-0000-000000000001",
            "reaction": "thumbs_up",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reaction"] == "thumbs_up"
    assert data["target_type"] == "quiz_question"


async def test_create_feedback_with_note(client: AsyncClient):
    """Submit feedforward (text note) on a reading."""
    resp = await client.post(
        "/api/v1/feedback",
        json={
            "target_type": "reading",
            "target_id": "00000000-0000-0000-0000-000000000002",
            "note": "More backend-oriented content please",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["note"] == "More backend-oriented content please"


async def test_list_feedback(client: AsyncClient):
    """List all feedback entries."""
    resp = await client.get("/api/v1/feedback")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_feedback_filtered_by_target(client: AsyncClient):
    """Filter feedback by target_type + target_id (UI hydration path)."""
    target_id = "00000000-0000-0000-0000-0000000000aa"

    # Seed: two reactions on the same reading + one on a different reading.
    await client.post(
        "/api/v1/feedback",
        json={
            "target_type": "reading",
            "target_id": target_id,
            "reaction": "thumbs_up",
        },
    )
    await client.post(
        "/api/v1/feedback",
        json={
            "target_type": "reading",
            "target_id": target_id,
            "note": "good stuff",
        },
    )
    await client.post(
        "/api/v1/feedback",
        json={
            "target_type": "reading",
            "target_id": "00000000-0000-0000-0000-0000000000bb",
            "reaction": "thumbs_down",
        },
    )

    resp = await client.get(
        "/api/v1/feedback",
        params={"target_type": "reading", "target_id": target_id},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert all(i["target_id"] == target_id for i in items)


async def test_list_disliked_target_ids_service(client: AsyncClient):
    """Thumbs-down rows are surfaced via the feedback listing filter."""
    target_id = "00000000-0000-0000-0000-0000000000cc"
    await client.post(
        "/api/v1/feedback",
        json={
            "target_type": "reading",
            "target_id": target_id,
            "reaction": "thumbs_down",
        },
    )
    resp = await client.get(
        "/api/v1/feedback",
        params={"target_type": "reading", "target_id": target_id},
    )
    assert resp.status_code == 200
    assert any(i["reaction"] == "thumbs_down" for i in resp.json())
