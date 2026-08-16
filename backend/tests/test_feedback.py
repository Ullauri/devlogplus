"""Tests for the feedback API endpoints."""

import uuid

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


# ---------------------------------------------------------------------------
# Latest reaction wins
# ---------------------------------------------------------------------------
# Feedback is an append-only log, so "did this ever get a thumbs-down" and "is
# this thumbs-downed now" are different questions. The pipelines need the
# second one; they used to ask the first.
async def test_latest_reaction_wins_when_user_changes_their_mind(client: AsyncClient, db_session):
    """An item rated up then down must not appear in both liked and disliked."""
    from backend.app.models.base import FeedbackTargetType
    from backend.app.services import feedback as feedback_svc

    target_id = "00000000-0000-0000-0000-0000000000d1"
    for reaction in ("thumbs_up", "thumbs_down"):
        resp = await client.post(
            "/api/v1/feedback",
            json={
                "target_type": "reading",
                "target_id": target_id,
                "reaction": reaction,
            },
        )
        assert resp.status_code == 201
        # Two separate clicks are two separate transactions in production. The
        # test client shares one session, and Postgres ``now()`` is
        # transaction-start time, so without this both rows would land on an
        # identical created_at and the ordering would be arbitrary.
        await db_session.commit()

    disliked = await feedback_svc.list_disliked_target_ids(db_session, FeedbackTargetType.READING)
    liked = await feedback_svc.list_liked_target_ids(db_session, FeedbackTargetType.READING)

    assert uuid.UUID(target_id) in disliked
    assert uuid.UUID(target_id) not in liked


async def test_cleared_reaction_is_retracted(client: AsyncClient, db_session):
    """Clearing a reaction writes a NULL row, which must retract the old one."""
    from backend.app.models.base import FeedbackTargetType
    from backend.app.services import feedback as feedback_svc

    target_id = "00000000-0000-0000-0000-0000000000d2"
    await client.post(
        "/api/v1/feedback",
        json={
            "target_type": "reading",
            "target_id": target_id,
            "reaction": "thumbs_down",
        },
    )
    await db_session.commit()  # see the note in the test above
    # The UI's "click again to clear" path: same item, no reaction.
    await client.post(
        "/api/v1/feedback",
        json={"target_type": "reading", "target_id": target_id, "note": "changed my mind"},
    )

    disliked = await feedback_svc.list_disliked_target_ids(db_session, FeedbackTargetType.READING)
    assert uuid.UUID(target_id) not in disliked
