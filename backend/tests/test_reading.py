"""Tests for the reading recommendations and allowlist API endpoints."""

import httpx
import pytest
from httpx import AsyncClient

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
