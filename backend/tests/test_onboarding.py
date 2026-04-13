"""Tests for the onboarding API endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_onboarding_status_before_completion(client: AsyncClient):
    """Before onboarding, status should show not completed."""
    resp = await client.get("/api/v1/onboarding/status")
    assert resp.status_code == 200
    assert resp.json()["completed"] is False


async def test_onboarding_state_before_completion(client: AsyncClient):
    """Before onboarding, state should return defaults."""
    resp = await client.get("/api/v1/onboarding/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed"] is False
    assert data["self_assessment"] is None


async def test_complete_onboarding(client: AsyncClient):
    """Completing onboarding stores the self-assessment and Go experience."""
    resp = await client.post(
        "/api/v1/onboarding/complete",
        json={
            "self_assessment": {
                "primary_languages": ["Python", "Go"],
                "years_experience": 5,
                "primary_domain": "backend",
                "comfort_areas": ["REST APIs", "SQL"],
                "growth_areas": ["distributed systems"],
            },
            "go_experience": {
                "level": "intermediate",
                "details": "Built a few CLI tools",
            },
            "topic_interests": ["concurrency", "testing"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed"] is True
    assert data["go_experience_level"] == "intermediate"
    assert data["completed_at"] is not None


async def test_onboarding_status_after_completion(client: AsyncClient):
    """After onboarding, status should show completed."""
    # Complete first
    await client.post(
        "/api/v1/onboarding/complete",
        json={
            "self_assessment": {
                "primary_languages": ["Python"],
                "years_experience": 3,
            },
            "go_experience": {"level": "beginner"},
        },
    )
    resp = await client.get("/api/v1/onboarding/status")
    assert resp.status_code == 200
    assert resp.json()["completed"] is True
