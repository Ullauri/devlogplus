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

from backend.app.services.llm.client import (
    EmptyLLMResponseError,
    _extract_message_content,
    _raise_for_status_with_body,
)


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


# --- Empty assistant content -------------------------------------------------
#
# A 200 with `content: null` is the shape a reasoning model returns when it
# spends the whole max_tokens budget thinking. Before this handling, that hit
# `content.strip()` and surfaced as `AttributeError: 'NoneType' object has no
# attribute 'strip'` from inside the client — pointing at string handling
# rather than at the token budget.


def test_content_is_returned_when_present() -> None:
    result = {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]}

    assert _extract_message_content(result, model="m", pipeline="quiz_generation") == '{"ok": true}'


def test_null_content_raises_instead_of_attributeerror() -> None:
    """The exact response shape observed on the failing project_generation run."""
    result = {
        "choices": [{"message": {"content": None}, "finish_reason": "length"}],
        "usage": {
            "completion_tokens": 8192,
            "completion_tokens_details": {"reasoning_tokens": 8192},
        },
    }

    with pytest.raises(EmptyLLMResponseError) as excinfo:
        _extract_message_content(
            result, model="anthropic/claude-sonnet-5", pipeline="project_generation"
        )

    message = str(excinfo.value)
    assert "finish_reason=length" in message
    assert "reasoning_tokens=8192" in message
    assert "pipeline=project_generation" in message
    # The actionable part — names both levers rather than leaving a bare error.
    assert "llm_reasoning_effort" in message
    assert "max_tokens" in message


def test_empty_string_content_is_also_an_error() -> None:
    result = {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}

    with pytest.raises(EmptyLLMResponseError):
        _extract_message_content(result, model="m", pipeline="topic_extraction")


def test_malformed_response_does_not_keyerror() -> None:
    """A response missing choices/message should still explain itself."""
    with pytest.raises(EmptyLLMResponseError) as excinfo:
        _extract_message_content({}, model="m", pipeline="reading_generation")

    assert "finish_reason=unknown" in str(excinfo.value)
