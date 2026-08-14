"""Tests for OpenRouter error surfacing.

Critical contract: when OpenRouter rejects a request, the reason must reach the
raised exception. OpenRouter returns a plain 400 for an invalid model ID, an
unsupported response_format, and an exhausted quota alike — the distinguishing
detail is only ever in the response body. httpx's bare ``raise_for_status()``
discards it, which makes every 4xx look identical in a traceback and sends you
looking at the wrong layer.
"""

import re

import httpx
import pytest

from backend.app.services.llm.client import (
    EmptyLLMResponseError,
    LLMJSONError,
    OpenRouterClient,
    _extract_message_content,
    _parse_json_content,
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


# --- JSON extraction ---------------------------------------------------------
#
# Anthropic models have no native json_object mode, so `response_format` is
# advisory over OpenRouter and the model may wrap its JSON in prose, a fence,
# or both. When no JSON can be read at all, the content itself has to reach the
# exception — a bare `JSONDecodeError: Expecting value: line 1 column 1` says
# only that the response didn't *begin* with JSON, which is true of a prose
# preamble and a refusal alike.


def _completion(finish_reason: str = "stop", **usage: object) -> dict[str, object]:
    return {"choices": [{"finish_reason": finish_reason}], "usage": usage}


def test_bare_json_object_parses() -> None:
    parsed = _parse_json_content('{"title": "x"}', _completion(), model="m", pipeline="p")

    assert parsed == {"title": "x"}


def test_fenced_json_parses() -> None:
    content = '```json\n{"title": "x"}\n```'

    assert _parse_json_content(content, _completion(), model="m", pipeline="p") == {"title": "x"}


def test_prose_preamble_before_a_fence_is_salvaged() -> None:
    """The observed project_generation failure: text before the opening fence."""
    content = 'Here is the project:\n\n```json\n{"title": "x", "files": []}\n```\n\nEnjoy!'

    parsed = _parse_json_content(
        content, _completion(), model="anthropic/claude-sonnet-5", pipeline="project_generation"
    )

    assert parsed == {"title": "x", "files": []}


def test_unfenced_object_behind_a_preamble_is_salvaged() -> None:
    content = 'Sure thing.\n{"title": "x"}'

    assert _parse_json_content(content, _completion(), model="m", pipeline="p") == {"title": "x"}


def test_braces_inside_string_values_survive_the_widest_span() -> None:
    """The brace-span salvage must not truncate at a nested or quoted brace."""
    content = 'Preamble.\n{"content": "func main() { fmt.Println(1) }", "n": {"a": 1}}'

    parsed = _parse_json_content(content, _completion(), model="m", pipeline="p")

    assert parsed["content"] == "func main() { fmt.Println(1) }"
    assert parsed["n"] == {"a": 1}


def test_unparseable_content_reaches_the_exception() -> None:
    content = "I can't generate that project."

    with pytest.raises(LLMJSONError) as excinfo:
        _parse_json_content(
            content, _completion(), model="anthropic/claude-sonnet-5", pipeline="project_generation"
        )

    message = str(excinfo.value)
    assert "I can't generate that project." in message
    assert "pipeline=project_generation" in message


def test_truncated_response_names_max_tokens_not_the_parser() -> None:
    content = '{"title": "x", "files": [{"path": "main.go", "content": "package ma'

    with pytest.raises(LLMJSONError) as excinfo:
        _parse_json_content(
            content,
            _completion("length", completion_tokens=8192),
            model="m",
            pipeline="project_generation",
        )

    message = str(excinfo.value)
    assert "truncated at max_tokens" in message
    assert "raise max_tokens for the project_generation pipeline" in message


def test_long_content_keeps_both_ends() -> None:
    """The tail is what distinguishes a truncated response from a prose one."""
    content = "PREAMBLE" + ("x" * 5000) + "ENDING"

    with pytest.raises(LLMJSONError) as excinfo:
        _parse_json_content(content, _completion(), model="m", pipeline="p")

    message = str(excinfo.value)
    assert "PREAMBLE" in message
    assert "ENDING" in message
    assert "5014 chars total" in message


def test_non_object_json_is_rejected() -> None:
    """The callers all expect a dict; a bare scalar is not an answer."""
    with pytest.raises(LLMJSONError):
        _parse_json_content("42", _completion(), model="m", pipeline="p")


# ── Complete-but-malformed responses ────────────────────────────────────────
# Raising max_tokens moved quiz_generation from finish_reason=length to
# finish_reason=stop, and it still failed: a complete, fenced, closed JSON
# object the decoder rejected. Head and tail both looked well-formed, so the
# error message said nothing useful about the defect in the elided middle.


def test_raw_newlines_in_strings_are_salvaged() -> None:
    """The quiz prompt invites a bulleted reference answer; models emit real
    newlines instead of \\n escapes, which strict json.loads rejects."""
    content = (
        '```json\n{"questions": [{"reference_answer": "Two points:\n'
        "- Contract tests check API shape.\n"
        '- E2E tests check journeys."}]}\n```'
    )

    parsed = _parse_json_content(content, _completion(), model="m", pipeline="quiz_generation")

    assert parsed["questions"][0]["reference_answer"].startswith("Two points:")


def _reported_offset(message: str) -> int:
    """Pull the char offset out of a decode-failure message.

    Asserting on a literal offset would pin the test to a CPython version:
    the same trailing comma is reported at char 23 on 3.13 and char 24 on
    3.12, which is the Python CI runs. What the message has to carry is *an*
    offset pointing into the content, not one exact number.
    """
    match = re.search(r"char (\d+)", message)
    assert match is not None, f"no char offset in message: {message}"
    return int(match.group(1))


def test_malformed_json_reports_the_offset_not_just_the_content() -> None:
    """Without the decoder's position the failure is indistinguishable from a
    parser bug, which is exactly what made this take two rounds to find."""
    # A trailing comma — complete and fenced, but invalid, and not something
    # the control-character salvage pass can rescue.
    content = '{"questions": [{"a": 1},]}'

    with pytest.raises(LLMJSONError) as excinfo:
        _parse_json_content(content, _completion(), model="m", pipeline="quiz_generation")

    message = str(excinfo.value)
    assert "malformed-JSON failure" in message
    assert "Content around that offset" in message
    # The break is the trailing comma near the end, not the opening brace.
    assert _reported_offset(message) > len(content) // 2


def test_offset_comes_from_the_furthest_candidate_not_the_first() -> None:
    """Candidate 0 is the raw fenced text and always dies at char 0. Reporting
    that instead of the real break is what buried the defect."""
    content = '```json\n{"questions": [{"a": 1},]}\n```'

    with pytest.raises(LLMJSONError) as excinfo:
        _parse_json_content(content, _completion(), model="m", pipeline="quiz_generation")

    message = str(excinfo.value)
    assert "malformed-JSON failure" in message
    assert _reported_offset(message) > 0


def test_offset_survives_an_earlier_control_character() -> None:
    """The salvage pass forgives control characters, so its failure is the real one.

    Regression, from a live quiz_generation response: a raw newline inside a
    reference answer at char 12209 and a genuine break at char 14509, where
    the model wrote ``"reference_answer="`` for ``"reference_answer": "``.
    Ranking strict failures only meant the message blamed the newline the
    salvage pass had already forgiven, and the run looked like a parser bug
    rather than a bad draw.
    """
    content = (
        '{"questions": [\n'
        '  {"reference_answer": "Two points:\nsecond line here"},\n'
        '  {"reference_answer"="missing the colon and quote"}\n'
        "]}"
    )
    control_char_offset = content.index("Two points:")

    with pytest.raises(LLMJSONError) as excinfo:
        _parse_json_content(content, _completion(), model="m", pipeline="quiz_generation")

    message = str(excinfo.value)
    assert "malformed-JSON failure" in message
    # The `=` is the break that no leniency can rescue; the newline is not.
    assert _reported_offset(message) > control_char_offset


def test_truncated_response_still_blames_max_tokens_not_the_json() -> None:
    """finish_reason=length keeps its own hint — a truncated object is also
    malformed, and the offset would be a red herring there."""
    content = '{"questions": [{"reference_answer": "unfinished'

    with pytest.raises(LLMJSONError) as excinfo:
        _parse_json_content(content, _completion("length"), model="m", pipeline="quiz_generation")

    message = str(excinfo.value)
    assert "truncated at max_tokens" in message
    assert "malformed-JSON failure" not in message


# ── Retrying a bad draw ─────────────────────────────────────────────────────
# Malformed JSON in a long response is a sampling accident, not a property of
# the prompt. Without a retry, one bad token costs the caller its whole result
# — for quiz_generation, the user's weekly quiz, with nothing on the page to
# say why it did not appear.


def _json_completion(content: str) -> dict[str, object]:
    return {
        "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        "usage": {},
    }


async def test_chat_completion_json_retries_a_malformed_draw(monkeypatch) -> None:
    client = OpenRouterClient()
    responses = [
        _json_completion('{"questions": [{"a": 1},]}'),  # trailing comma
        _json_completion('{"questions": [{"a": 1}]}'),
    ]
    calls: list[dict] = []

    async def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return responses[len(calls) - 1]

    monkeypatch.setattr(client, "chat_completion", fake_chat_completion)

    parsed = await client.chat_completion_json(
        pipeline="quiz_generation", messages=[], json_retries=1
    )

    assert parsed == {"questions": [{"a": 1}]}
    assert len(calls) == 2


async def test_chat_completion_json_gives_up_after_the_last_retry(monkeypatch) -> None:
    """The error still reaches the caller — a retry budget is not a swallow."""
    client = OpenRouterClient()
    calls: list[dict] = []

    async def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return _json_completion('{"questions": [{"a": 1},]}')

    monkeypatch.setattr(client, "chat_completion", fake_chat_completion)

    with pytest.raises(LLMJSONError):
        await client.chat_completion_json(pipeline="quiz_generation", messages=[], json_retries=1)

    assert len(calls) == 2


async def test_chat_completion_json_does_not_retry_by_default(monkeypatch) -> None:
    """Callers opt in. A truncation would only repeat at double the cost."""
    client = OpenRouterClient()
    calls: list[dict] = []

    async def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return _json_completion('{"questions": [{"a": 1},]}')

    monkeypatch.setattr(client, "chat_completion", fake_chat_completion)

    with pytest.raises(LLMJSONError):
        await client.chat_completion_json(pipeline="quiz_generation", messages=[])

    assert len(calls) == 1
