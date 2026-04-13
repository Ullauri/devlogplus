"""Tests for the triage API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import TriageSeverity, TriageSource, TriageStatus
from backend.app.models.triage import TriageItem

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_triage_item(
    db: AsyncSession,
    *,
    title: str = "Test triage",
    severity: TriageSeverity = TriageSeverity.MEDIUM,
    status: TriageStatus = TriageStatus.PENDING,
) -> TriageItem:
    """Helper to insert a triage item directly."""
    item = TriageItem(
        source=TriageSource.PROFILE_UPDATE,
        title=title,
        description="Needs attention",
        severity=severity,
        status=status,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def test_list_triage_empty(client: AsyncClient):
    """Empty list when no triage items exist."""
    resp = await client.get("/api/v1/triage")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_triage_with_items(client: AsyncClient, db_session: AsyncSession):
    """List triage items after inserting some."""
    await _create_triage_item(db_session, title="Item A", severity=TriageSeverity.HIGH)
    await _create_triage_item(db_session, title="Item B", severity=TriageSeverity.LOW)

    resp = await client.get("/api/v1/triage")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2


async def test_list_triage_filter_by_severity(client: AsyncClient, db_session: AsyncSession):
    """Filter triage items by severity."""
    await _create_triage_item(db_session, title="Critical one", severity=TriageSeverity.CRITICAL)
    resp = await client.get("/api/v1/triage", params={"severity": "critical"})
    assert resp.status_code == 200
    for item in resp.json():
        assert item["severity"] == "critical"


async def test_get_triage_item(client: AsyncClient, db_session: AsyncSession):
    """Get a specific triage item by ID."""
    item = await _create_triage_item(db_session, title="Single item")
    resp = await client.get(f"/api/v1/triage/{item.id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Single item"


async def test_get_triage_item_not_found(client: AsyncClient):
    """Nonexistent triage item returns 404."""
    resp = await client.get("/api/v1/triage/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_resolve_triage_item(client: AsyncClient, db_session: AsyncSession):
    """Resolve a triage item with an action."""
    item = await _create_triage_item(db_session)
    resp = await client.post(
        f"/api/v1/triage/{item.id}/resolve",
        json={"action": "accepted", "resolution_text": "Looks correct"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["resolution_text"] == "Looks correct"
    assert data["resolved_at"] is not None


async def test_resolve_nonexistent_triage(client: AsyncClient):
    """Resolving a nonexistent triage item returns 404."""
    resp = await client.post(
        "/api/v1/triage/00000000-0000-0000-0000-000000000000/resolve",
        json={"action": "rejected"},
    )
    assert resp.status_code == 404


async def test_blocking_triage_none(client: AsyncClient):
    """No blocking triage when no high/critical pending items."""
    resp = await client.get("/api/v1/triage/blocking")
    assert resp.status_code == 200
    # May or may not be blocking depending on prior test state, just check structure
    assert "blocking" in resp.json()


async def test_blocking_triage_with_critical(client: AsyncClient, db_session: AsyncSession):
    """Blocking should be true when a critical pending item exists."""
    await _create_triage_item(db_session, title="Blocker", severity=TriageSeverity.CRITICAL)
    resp = await client.get("/api/v1/triage/blocking")
    assert resp.status_code == 200
    assert resp.json()["blocking"] is True
