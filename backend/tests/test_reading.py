"""Tests for the reading recommendations and allowlist API endpoints."""

from datetime import date, timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import ReadingRecommendationType
from backend.app.models.reading import ReadingRecommendation
from backend.app.services import reading as reading_svc

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
async def test_list_recommendations_empty(client: AsyncClient):
    """Empty paginated envelope when no recommendations exist."""
    resp = await client.get("/api/v1/readings/recommendations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["offset"] == 0
    assert body["limit"] == 20


# ---------------------------------------------------------------------------
# Per-item state (read / saved / dismissed)
# ---------------------------------------------------------------------------
async def _make_rec(
    db: AsyncSession, *, batch_date: date, title: str = "T"
) -> ReadingRecommendation:
    rec = ReadingRecommendation(
        title=title,
        url=f"https://example.com/{title}",
        source_domain="example.com",
        description=None,
        topic_id=None,
        recommendation_type=ReadingRecommendationType.DEEP_DIVE,
        batch_date=batch_date,
    )
    db.add(rec)
    await db.flush()
    return rec


async def test_fresh_recommendation_is_unread(client: AsyncClient, db_session: AsyncSession):
    """Newly generated items default to status='unread' with all timestamps null."""
    rec = await _make_rec(db_session, batch_date=date.today())
    await db_session.commit()

    resp = await client.get("/api/v1/readings/recommendations")
    assert resp.status_code == 200
    items = resp.json()["items"]
    item = next(i for i in items if i["id"] == str(rec.id))
    assert item["status"] == "unread"
    assert item["read_at"] is None
    assert item["saved_at"] is None
    assert item["dismissed_at"] is None


async def test_mark_read_sets_status_and_timestamp(client: AsyncClient, db_session: AsyncSession):
    rec = await _make_rec(db_session, batch_date=date.today())
    await db_session.commit()

    resp = await client.patch(f"/api/v1/readings/recommendations/{rec.id}", json={"read": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "read"
    assert data["read_at"] is not None
    assert data["dismissed_at"] is None


async def test_mark_read_is_idempotent(client: AsyncClient, db_session: AsyncSession):
    """Re-marking an item as read preserves the original timestamp."""
    rec = await _make_rec(db_session, batch_date=date.today())
    await db_session.commit()

    first = await client.patch(f"/api/v1/readings/recommendations/{rec.id}", json={"read": True})
    second = await client.patch(f"/api/v1/readings/recommendations/{rec.id}", json={"read": True})
    assert first.json()["read_at"] == second.json()["read_at"]


async def test_dismiss_clears_saved(client: AsyncClient, db_session: AsyncSession):
    """Dismissing an item implicitly clears the saved flag."""
    rec = await _make_rec(db_session, batch_date=date.today())
    await db_session.commit()

    await client.patch(f"/api/v1/readings/recommendations/{rec.id}", json={"saved": True})
    resp = await client.patch(
        f"/api/v1/readings/recommendations/{rec.id}", json={"dismissed": True}
    )
    data = resp.json()
    assert data["status"] == "dismissed"
    assert data["saved_at"] is None
    assert data["dismissed_at"] is not None


async def test_save_clears_dismissed(client: AsyncClient, db_session: AsyncSession):
    """Saving an item un-dismisses it."""
    rec = await _make_rec(db_session, batch_date=date.today())
    await db_session.commit()

    await client.patch(f"/api/v1/readings/recommendations/{rec.id}", json={"dismissed": True})
    resp = await client.patch(f"/api/v1/readings/recommendations/{rec.id}", json={"saved": True})
    data = resp.json()
    assert data["status"] == "saved"
    assert data["dismissed_at"] is None
    assert data["saved_at"] is not None


async def test_patch_unknown_id_returns_404(client: AsyncClient):
    resp = await client.patch(
        "/api/v1/readings/recommendations/00000000-0000-0000-0000-000000000000",
        json={"read": True},
    )
    assert resp.status_code == 404


async def test_active_only_excludes_old_unread_and_dismissed(
    client: AsyncClient, db_session: AsyncSession
):
    """Active list = latest batch + saved items from prior batches, minus dismissed."""
    today = date.today()
    old = today - timedelta(days=14)

    old_unread = await _make_rec(db_session, batch_date=old, title="old-unread")
    old_saved = await _make_rec(db_session, batch_date=old, title="old-saved")
    current = await _make_rec(db_session, batch_date=today, title="current")
    current_dismissed = await _make_rec(db_session, batch_date=today, title="current-dismissed")
    await db_session.commit()

    # Mark the old one as saved and the current one as dismissed.
    await client.patch(f"/api/v1/readings/recommendations/{old_saved.id}", json={"saved": True})
    await client.patch(
        f"/api/v1/readings/recommendations/{current_dismissed.id}", json={"dismissed": True}
    )

    resp = await client.get("/api/v1/readings/recommendations?active_only=true")
    assert resp.status_code == 200
    ids = {i["id"] for i in resp.json()["items"]}

    assert str(current.id) in ids
    assert str(old_saved.id) in ids
    assert str(old_unread.id) not in ids  # old & not saved → dropped
    assert str(current_dismissed.id) not in ids  # dismissed → dropped

    # Without the filter, the full archive is returned.
    resp_all = await client.get("/api/v1/readings/recommendations")
    all_ids = {i["id"] for i in resp_all.json()["items"]}
    assert {str(old_unread.id), str(current_dismissed.id)} <= all_ids


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


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------
async def test_validate_urls_empty_input():
    """Empty input yields empty output and performs zero requests."""
    result = await reading_svc.validate_urls([])
    assert result == {}


async def test_validate_urls_mixed_success_and_404(monkeypatch):
    """Validator marks 2xx/3xx as reachable and 4xx/5xx as unreachable."""
    status_by_url = {
        "https://ok.example.com/a": 200,
        "https://redir.example.com/b": 301,
        "https://gone.example.com/c": 404,
        "https://broken.example.com/d": 500,
    }

    def _transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_by_url[str(request.url)])

    transport = httpx.MockTransport(_transport)

    # Patch AsyncClient to use the mock transport
    real_client = httpx.AsyncClient

    def _fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(reading_svc.httpx, "AsyncClient", _fake_client)

    result = await reading_svc.validate_urls(list(status_by_url.keys()), timeout=1.0)

    assert result["https://ok.example.com/a"] == (True, None)
    assert result["https://redir.example.com/b"] == (True, None)
    assert result["https://gone.example.com/c"][0] is False
    assert "404" in result["https://gone.example.com/c"][1]
    assert result["https://broken.example.com/d"][0] is False
    assert "500" in result["https://broken.example.com/d"][1]


async def test_validate_urls_falls_back_to_get_on_405(monkeypatch):
    """Servers that reject HEAD should be retried with GET."""
    calls: list[str] = []

    def _transport(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "HEAD":
            return httpx.Response(405)
        return httpx.Response(200)

    transport = httpx.MockTransport(_transport)
    real_client = httpx.AsyncClient

    def _fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(reading_svc.httpx, "AsyncClient", _fake_client)

    result = await reading_svc.validate_urls(["https://picky.example.com/x"], timeout=1.0)

    assert result["https://picky.example.com/x"] == (True, None)
    assert calls == ["HEAD", "GET"]


async def test_validate_urls_timeout(monkeypatch):
    """Network timeouts are translated into ``(False, 'timeout')``."""

    def _transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated timeout", request=request)

    transport = httpx.MockTransport(_transport)
    real_client = httpx.AsyncClient

    def _fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(reading_svc.httpx, "AsyncClient", _fake_client)

    result = await reading_svc.validate_urls(["https://slow.example.com/"], timeout=0.5)

    ok, reason = result["https://slow.example.com/"]
    assert ok is False
    assert reason == "timeout"


async def test_validate_urls_deduplicates(monkeypatch):
    """Duplicate URLs only trigger a single HTTP request."""
    hits: list[str] = []

    def _transport(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        return httpx.Response(200)

    transport = httpx.MockTransport(_transport)
    real_client = httpx.AsyncClient

    def _fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(reading_svc.httpx, "AsyncClient", _fake_client)

    await reading_svc.validate_urls(
        [
            "https://dup.example.com/page",
            "https://dup.example.com/page",
            "https://dup.example.com/page",
        ],
        timeout=1.0,
    )

    assert len(hits) == 1


# ---------------------------------------------------------------------------
# Bug 3 (Issue #7): seed_default_allowlist() must include batch-2 domains
# ---------------------------------------------------------------------------


async def test_seed_default_allowlist_includes_batch2_domains(db_session: AsyncSession):
    """seed_default_allowlist() must seed at least 68 entries (batch 1 + batch 2).

    Bug: DEFAULT_ALLOWLIST in reading.py only contained the 37 batch-1 entries.
    Migration 005 added 31 more (batch 2), but seed_default_allowlist() was
    never updated to include them, so calling it independently produced an
    incomplete set.
    """
    from sqlalchemy import func
    from sqlalchemy import select as sa_select

    from backend.app.models.reading import ReadingAllowlist

    # Call the seeder on the empty test DB.
    await reading_svc.seed_default_allowlist(db_session)
    await db_session.commit()

    # Count only the default entries to be precise.
    stmt = (
        sa_select(func.count())
        .select_from(ReadingAllowlist)
        .where(
            ReadingAllowlist.is_default == True  # noqa: E712
        )
    )
    result = await db_session.execute(stmt)
    total = result.scalar_one()

    assert total >= 68, (
        f"Expected at least 68 default allowlist entries (batch 1 + batch 2), "
        f"got {total}. seed_default_allowlist() is missing batch-2 domains."
    )
