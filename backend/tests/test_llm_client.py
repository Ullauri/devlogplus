"""Tests for OpenRouter error surfacing.

Critical contract: when OpenRouter rejects a request, the reason must reach the
raised exception. OpenRouter returns a plain 400 for an invalid model ID, an
unsupported response_format, and an exhausted quota alike — the distinguishing
detail is only ever in the response body. httpx's bare ``raise_for_status()``
discards it, which makes every 4xx look identical in a traceback and sends you
looking at the wrong layer.
"""

import httpx
import pytest

from backend.app.services.llm.client import _raise_for_status_with_body


def _response(status: int, text: str) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        text=text,
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )


def test_success_does_not_raise() -> None:
    _raise_for_status_with_body(
        _response(200, '{"choices": []}'),
        model="anthropic/claude-sonnet-5",
        pipeline="quiz_generation",
    )


def test_error_body_reaches_the_exception() -> None:
    body = '{"error":{"message":"anthropic/bogus-model is not a valid model ID","code":400}}'

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        _raise_for_status_with_body(
            _response(400, body), model="anthropic/bogus-model", pipeline="project_generation"
        )

    message = str(excinfo.value)
    # The actionable part: without this the traceback says only "400 Bad Request".
    assert "is not a valid model ID" in message
    # Which pipeline and model, so a 7-pipeline app doesn't need a bisect.
    assert "pipeline=project_generation" in message
    assert "model=anthropic/bogus-model" in message


def test_raises_the_same_exception_type() -> None:
    """Existing ``except httpx.HTTPStatusError`` handlers must keep working."""
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        _raise_for_status_with_body(
            _response(429, "rate limited"), model="m", pipeline="quiz_evaluation"
        )

    assert excinfo.value.response.status_code == 429
    assert excinfo.value.request is not None


def test_empty_body_is_labelled_not_silent() -> None:
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        _raise_for_status_with_body(_response(502, ""), model="m", pipeline="reading_generation")

    assert "<empty response body>" in str(excinfo.value)


def test_long_body_is_truncated_and_says_so() -> None:
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        _raise_for_status_with_body(
            _response(400, "x" * 5000), model="m", pipeline="topic_extraction"
        )

    message = str(excinfo.value)
    assert "truncated, 5000 bytes total" in message
    # Bounded so a huge upstream error can't flood the logs.
    assert len(message) < 3000
