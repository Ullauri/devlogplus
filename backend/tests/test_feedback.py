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
