"""Tests for the Decisions (Jev) client.

Critical contract: the client never raises into a pipeline. No key, a
timeout, an HTTP error and an unreadable body all come back as ``None``, and
the caller falls back to what it did before the gate existed. Request
building and response parsing are tested against a recorded response; no
test here reaches the network.
"""

import asyncio
import json
import logging

import pytest

from backend.app.config import settings
from backend.app.services.llm.decisions import (
    DECISIONS_URL,
    JEV_MODEL,
    DecisionsClient,
    DecisionsError,
    NoulDecision,
    build_request,
    decisions_client,
    noul,
    parse_noul_response,
)

# The shape of homechan's recorded reply of 2026-09-19 (typesafe/jev-1.13),
# reduced to the one noul answer this client asks for. Usage figures are the
# recorded ones.
RECORDED = {
    "answers": {"q": {"type": "noul", "noul": 0.06}},
    "usage": {"input_tokens": 423, "output_tokens": 70, "cost": 0.000018},
    "provider": "TypeSafe",
    "model": "typesafe/jev-1.13-20260917",
}

SECRET_ENTRY = "the entry text must never reach a log line"


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key-not-real")


def _client_answering(status: int, body, seen: list | None = None) -> DecisionsClient:
    client = DecisionsClient()

    async def _post(payload):
        if seen is not None:
            seen.append(payload)
        return status, body

    client._post = _post  # type: ignore[method-assign]
    return client


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------
def test_request_shape_matches_the_api() -> None:
    request = build_request("hello", {"q": noul("Is it?")})
    assert request == {
        "model": JEV_MODEL,
        "state": "hello",
        "questions": {"q": {"type": "noul", "instructions": "Is it?"}},
    }
    json.dumps(request)


def test_request_needs_a_question() -> None:
    with pytest.raises(ValueError):
        build_request("hello", {})


def test_parses_the_recorded_response() -> None:
    decision = parse_noul_response(RECORDED, "q")
    assert decision == NoulDecision(
        p_yes=0.06,
        input_tokens=423,
        output_tokens=70,
        cost=0.000018,
        model="typesafe/jev-1.13-20260917",
    )


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"message": "invalid model", "code": 400}},
        {"error": "plain string error"},
        {"not": "answers"},
        {"answers": {}},
        {"answers": {"q": {"type": "choice", "choice": "a"}}},
        {"answers": {"q": {"type": "noul"}}},
        {"answers": {"q": {"type": "noul", "noul": "high"}}},
        {"answers": {"q": {"type": "noul", "noul": 1.7}}},
        {"answers": {"q": {"type": "noul", "noul": 0.5}}, "usage": "free"},
        ["not", "an", "object"],
    ],
)
def test_unreadable_bodies_raise_decisions_error(body) -> None:
    with pytest.raises(DecisionsError):
        parse_noul_response(body, "q")


# ---------------------------------------------------------------------------
# The client: fail soft, every way
# ---------------------------------------------------------------------------
async def test_no_key_means_no_opinion_and_no_request(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    seen: list = []
    client = _client_answering(200, RECORDED, seen)

    assert await client.ask_noul(pipeline="entry_gate", state="x", question="?") is None
    assert seen == []


async def test_recorded_reply_through_the_client(with_key) -> None:
    seen: list = []
    client = _client_answering(200, RECORDED, seen)

    decision = await client.ask_noul(pipeline="entry_gate", state="some entry", question="Is it?")

    assert decision is not None
    assert decision.p_yes == pytest.approx(0.06)
    assert seen == [build_request("some entry", {"q": noul("Is it?")})]


async def test_timeout_is_no_opinion(with_key) -> None:
    client = DecisionsClient(timeout=0.05)

    async def _slow(payload):
        await asyncio.sleep(1)
        return 200, RECORDED

    client._post = _slow  # type: ignore[method-assign]

    assert await client.ask_noul(pipeline="entry_gate", state="x", question="?") is None


def test_default_timeout_is_at_most_three_seconds() -> None:
    assert decisions_client.timeout <= 3.0
    assert decisions_client.url == DECISIONS_URL
    assert decisions_client.model == JEV_MODEL


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (500, {"error": {"message": "upstream down"}}),
        (502, "<html>Bad gateway</html>"),
        (401, {"unexpected": "shape"}),
        (200, {"error": {"message": "invalid model"}}),
        (200, {"answers": {"q": {"type": "score", "score": 1.0}}}),
        (200, "not json at all"),
    ],
)
async def test_http_errors_and_bad_bodies_are_no_opinion(with_key, status, body) -> None:
    client = _client_answering(status, body)
    assert await client.ask_noul(pipeline="entry_gate", state="x", question="?") is None


async def test_transport_errors_are_no_opinion(with_key) -> None:
    client = DecisionsClient()

    async def _boom(payload):
        raise ConnectionResetError("connection reset")

    client._post = _boom  # type: ignore[method-assign]

    assert await client.ask_noul(pipeline="entry_gate", state="x", question="?") is None


async def test_logs_the_numbers_and_never_the_text(with_key, caplog) -> None:
    client = _client_answering(200, RECORDED)

    with caplog.at_level(logging.INFO):
        await client.ask_noul(pipeline="entry_gate", state=SECRET_ENTRY, question="?")

    lines = [r.getMessage() for r in caplog.records]
    gate_lines = [line for line in lines if line.startswith("Decisions [entry_gate]")]
    assert len(gate_lines) == 1
    for part in ("p_yes=0.060", "in=423", "out=70", "cost=$0.000018", "ms"):
        assert part in gate_lines[0]
    assert not any(SECRET_ENTRY in line for line in lines)


async def test_failures_never_log_the_text(with_key, caplog) -> None:
    client = _client_answering(500, {"error": {"message": "boom"}})

    with caplog.at_level(logging.INFO):
        await client.ask_noul(pipeline="entry_gate", state=SECRET_ENTRY, question="?")

    assert not any(SECRET_ENTRY in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# The suite's own seal
# ---------------------------------------------------------------------------
async def test_the_offline_suite_cannot_reach_the_decisions_endpoint(with_key) -> None:
    """With a key set and nothing patched, the request is refused, loudly.

    ``_no_real_decisions_calls`` replaces ``DecisionsClient._post``. Its error
    is a ``BaseException`` so the client's fail-soft handler cannot turn the
    leak into a quiet "no opinion".
    """
    with pytest.raises(BaseException, match="reached the real Decisions API"):
        await decisions_client.ask_noul(pipeline="entry_gate", state="x", question="?")
