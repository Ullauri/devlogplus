"""OpenRouter LLM client — single integration point for all LLM calls."""

import json
import logging
import re
from typing import Any

import httpx

from backend.app.config import settings
from backend.app.services.llm.tracing import trace_llm_call

logger = logging.getLogger(__name__)

# OpenRouter puts the actionable reason in the response body, not the status
# line: an invalid model ID, an unsupported response_format, and an exhausted
# quota are all plain 400s. httpx's raise_for_status() reports only the status,
# so the reason was being discarded at the point of failure and every 4xx
# looked identical in the logs.
_ERROR_BODY_LIMIT = 2000

# How much of an unparseable response to carry in the exception. The tail
# matters as much as the head: a response that ends mid-token was truncated,
# one that ends with prose or a closing fence was not. Guessing between those
# two from a bare JSONDecodeError is exactly what costs the time.
_CONTENT_HEAD_LIMIT = 1200
_CONTENT_TAIL_LIMIT = 400

# Head and tail are useless when the break is in the middle: a response whose
# first and last 1600 chars are well-formed reads as "complete JSON the parser
# refused", which says nothing about the actual defect. This window is quoted
# around the decoder's reported offset instead.
_DECODE_WINDOW_BEFORE = 120
_DECODE_WINDOW_AFTER = 80

# Models routinely wrap the JSON they were asked for in prose ("Here's the
# project:") and a code fence. Anthropic models have no native json_object
# mode, so `response_format` is advisory at best over OpenRouter.
_JSON_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


class EmptyLLMResponseError(RuntimeError):
    """The API returned 200 but the assistant message carried no text.

    Most often the response was truncated at ``max_tokens``: OpenRouter counts
    reasoning as output tokens, so a reasoning model can spend the entire
    budget thinking and emit no answer at all. ``content`` is then ``null``
    rather than a partial string.
    """


class LLMJSONError(RuntimeError):
    """The assistant returned text, but no JSON object could be read from it."""


def _finish_reason(result: dict[str, Any]) -> str:
    choice = (result.get("choices") or [{}])[0]
    return choice.get("finish_reason") or choice.get("native_finish_reason") or "unknown"


def _usage_summary(result: dict[str, Any]) -> str:
    usage = result.get("usage") or {}
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    return (
        f"completion_tokens={usage.get('completion_tokens')}, "
        f"reasoning_tokens={reasoning_tokens}"
    )


def _extract_message_content(result: dict[str, Any], *, model: str, pipeline: str) -> str:
    """Pull the assistant text out of a completion, or explain why it's absent."""
    choice = (result.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content")
    if content:
        return content

    finish_reason = _finish_reason(result)
    hint = ""
    if finish_reason == "length":
        hint = (
            " The response hit max_tokens. Reasoning tokens count toward the same budget, "
            "so either lower settings.llm_reasoning_effort or raise this pipeline's max_tokens."
        )

    raise EmptyLLMResponseError(
        f"No content returned for pipeline={pipeline} model={model} "
        f"(finish_reason={finish_reason}, {_usage_summary(result)}).{hint}"
    )


def _json_candidates(content: str) -> list[str]:
    """Progressively looser readings of a response that should contain JSON.

    Ordered strictest first, so a well-formed response is parsed exactly as it
    was sent and the salvage paths only run once that has failed.
    """
    text = content.strip()
    candidates = [text]

    # A fence at the very start — the shape the model produces when it obeys
    # "respond with JSON" but still reaches for markdown.
    unfenced = re.sub(r"^```(?:json)?\s*\n?", "", text)
    candidates.append(re.sub(r"\n?```\s*$", "", unfenced).strip())

    # A fenced block anywhere, for when prose precedes it.
    candidates.extend(match.group(1).strip() for match in _JSON_FENCE.finditer(text))

    # Widest brace span: an unfenced object behind a preamble.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    return candidates


def _describe_decode_failure(candidate: str, exc: json.JSONDecodeError) -> str:
    """Quote the span around a decoder's reported offset."""
    start = max(0, exc.pos - _DECODE_WINDOW_BEFORE)
    window = candidate[start : exc.pos + _DECODE_WINDOW_AFTER]
    return (
        f"{exc.msg} at line {exc.lineno} column {exc.colno} (char {exc.pos}). "
        f"Content around that offset: {window!r}"
    )


def _parse_json_content(
    content: str, result: dict[str, Any], *, model: str, pipeline: str
) -> dict[str, Any]:
    """Read a JSON object out of an assistant response, or say why we couldn't."""
    candidates: list[str] = []
    seen: set[str] = set()
    for candidate in _json_candidates(content):
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)

    # The furthest-reaching failure of any pass, kept for the error message.
    # Position is the right ranking: the earliest candidates are deliberately
    # loose readings that die at char 0 on the opening fence, and reporting
    # that instead of the real defect is what makes these failures opaque.
    #
    # Both passes count. Ranking strict failures only meant that whenever the
    # salvage pass got further — which is its whole purpose — the reported
    # cause was the control character it had already forgiven, not the defect
    # that actually sank the parse. One real case: a response reported as
    # "invalid control character at char 12209" was in truth rejected at char
    # 14509, where the model wrote `"reference_answer="` for `"reference_answer": "`.
    deepest: tuple[str, json.JSONDecodeError] | None = None

    # Strict first, so a well-formed response is parsed exactly as sent. The
    # salvage pass only relaxes control characters inside strings — the shape
    # a model produces when a prompt invites a multi-line answer (this one asks
    # for "a short bulleted list when that's genuinely clearer") and it emits
    # real newlines instead of \n escapes. Nothing else about JSON is loosened.
    for strict in (True, False):
        for candidate in candidates:
            try:
                parsed = json.loads(candidate, strict=strict)
            except json.JSONDecodeError as exc:
                if deepest is None or exc.pos > deepest[1].pos:
                    deepest = (candidate, exc)
                continue
            if isinstance(parsed, dict):
                if not strict:
                    logger.warning(
                        "Recovered JSON for pipeline=%s model=%s only by allowing raw control "
                        "characters in strings — the model emitted literal newlines instead of "
                        "escapes.",
                        pipeline,
                        model,
                    )
                return parsed

    finish_reason = _finish_reason(result)
    head = content[:_CONTENT_HEAD_LIMIT]
    tail = ""
    if len(content) > _CONTENT_HEAD_LIMIT + _CONTENT_TAIL_LIMIT:
        tail = f"\n… [{len(content)} chars total] …\n{content[-_CONTENT_TAIL_LIMIT:]}"

    hint = ""
    if finish_reason == "length":
        hint = (
            " The response was truncated at max_tokens, so the JSON was never closed — "
            f"raise max_tokens for the {pipeline} pipeline rather than looking at the parser."
        )
    elif deepest is not None:
        # A complete response the decoder still rejects. Without the offset this
        # reads as "the parser is broken", and the actual defect is invisible
        # because it sits in the elided middle of the content.
        hint = f" The response was complete, so this is a malformed-JSON failure: {
            _describe_decode_failure(*deepest)
        }"

    message = (
        f"No JSON object found in the response for pipeline={pipeline} model={model} "
        f"(finish_reason={finish_reason}, {_usage_summary(result)}).{hint}\n"
        f"Assistant content was:\n{head}{tail}"
    )
    logger.error("%s", message)
    raise LLMJSONError(message)


def _raise_for_status_with_body(response: httpx.Response, *, model: str, pipeline: str) -> None:
    """raise_for_status(), but carrying OpenRouter's explanation.

    Re-raises the same ``httpx.HTTPStatusError`` type so existing handlers keep
    working; only the message is enriched.
    """
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text[:_ERROR_BODY_LIMIT] or "<empty response body>"
        if len(response.text) > _ERROR_BODY_LIMIT:
            body += f"… [truncated, {len(response.text)} bytes total]"
        message = (
            f"{exc}\n" f"pipeline={pipeline} model={model}\n" f"OpenRouter response body: {body}"
        )
        logger.error(
            "OpenRouter %s for pipeline=%s model=%s: %s",
            response.status_code,
            pipeline,
            model,
            body,
        )
        raise httpx.HTTPStatusError(message, request=exc.request, response=exc.response) from exc


class OpenRouterClient:
    """Async HTTP client for the OpenRouter API.

    All LLM calls in the application go through this client.
    Model selection is config-driven via ``settings.model_for_pipeline()``.
    """

    def __init__(self) -> None:
        self.base_url = settings.openrouter_base_url.rstrip("/")
        self.api_key = settings.openrouter_api_key
        self._http: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://devlogplus.local",
                    "X-Title": "DevLog+",
                },
                timeout=120.0,
            )
        return self._http

    async def chat_completion(
        self,
        *,
        pipeline: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request through OpenRouter.

        Args:
            pipeline: Pipeline name — used for model selection and Langfuse tracing.
            messages: Chat messages in OpenAI format.
            temperature: Sampling temperature.
            max_tokens: Max tokens in the response.
            response_format: Optional JSON schema for structured output.

        Returns:
            The full API response as a dict.
        """
        model = settings.model_for_pipeline(pipeline)
        client = await self._get_client()

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if settings.llm_reasoning_effort:
            payload["reasoning"] = {"effort": settings.llm_reasoning_effort}

        # Trace through Langfuse
        with trace_llm_call(
            pipeline=pipeline,
            model=model,
            input_data={"messages": messages},
        ) as trace:
            response = await client.post("/chat/completions", json=payload)
            _raise_for_status_with_body(response, model=model, pipeline=pipeline)
            result = response.json()

            # Truncation is silent otherwise: the caller gets a plausible-looking
            # partial answer and only notices downstream, if at all.
            if _finish_reason(result) == "length":
                logger.warning(
                    "Response truncated at max_tokens=%s for pipeline=%s model=%s (%s)",
                    max_tokens,
                    pipeline,
                    model,
                    _usage_summary(result),
                )

            # Record output and usage in the trace
            trace.record_output(result)

            return result

    async def chat_completion_text(
        self,
        *,
        pipeline: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Convenience: return just the assistant's text response."""
        result = await self.chat_completion(
            pipeline=pipeline,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _extract_message_content(
            result, model=settings.model_for_pipeline(pipeline), pipeline=pipeline
        )

    async def chat_completion_json(
        self,
        *,
        pipeline: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        json_retries: int = 0,
    ) -> dict[str, Any]:
        """Convenience: parse the assistant's response as JSON.

        ``json_retries`` re-requests on a malformed-JSON failure. Sampling is
        what produces these — a long response where one key came out as
        ``"reference_answer="`` — so the same prompt usually parses on the next
        draw, and without a retry a single bad token costs the caller its whole
        result. Only :class:`LLMJSONError` is retried: a truncation
        (``finish_reason=length``) or an empty response is a budget problem
        that a second identical request would only repeat, at double the cost.
        """
        model = settings.model_for_pipeline(pipeline)
        attempts = max(json_retries, 0) + 1
        for attempt in range(attempts):
            result = await self.chat_completion(
                pipeline=pipeline,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = _extract_message_content(result, model=model, pipeline=pipeline)
            try:
                return _parse_json_content(content, result, model=model, pipeline=pipeline)
            except LLMJSONError:
                if attempt + 1 >= attempts:
                    raise
                logger.warning(
                    "Malformed JSON from pipeline=%s model=%s — retrying (attempt %d of %d).",
                    pipeline,
                    model,
                    attempt + 2,
                    attempts,
                )
        raise AssertionError("unreachable: loop returns or raises")  # pragma: no cover

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()


# Module-level singleton
llm_client = OpenRouterClient()
