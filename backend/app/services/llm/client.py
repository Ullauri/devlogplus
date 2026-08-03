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


class EmptyLLMResponseError(RuntimeError):
    """The API returned 200 but the assistant message carried no text.

    Most often the response was truncated at ``max_tokens``: OpenRouter counts
    reasoning as output tokens, so a reasoning model can spend the entire
    budget thinking and emit no answer at all. ``content`` is then ``null``
    rather than a partial string.
    """


def _extract_message_content(result: dict[str, Any], *, model: str, pipeline: str) -> str:
    """Pull the assistant text out of a completion, or explain why it's absent."""
    choice = (result.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content")
    if content:
        return content

    finish_reason = choice.get("finish_reason") or choice.get("native_finish_reason") or "unknown"
    usage = result.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")

    hint = ""
    if finish_reason == "length":
        hint = (
            " The response hit max_tokens. Reasoning tokens count toward the same budget, "
            "so either lower settings.llm_reasoning_effort or raise this pipeline's max_tokens."
        )

    raise EmptyLLMResponseError(
        f"No content returned for pipeline={pipeline} model={model} "
        f"(finish_reason={finish_reason}, completion_tokens={completion_tokens}, "
        f"reasoning_tokens={reasoning_tokens}).{hint}"
    )


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
    ) -> dict[str, Any]:
        """Convenience: parse the assistant's response as JSON."""
        result = await self.chat_completion(
            pipeline=pipeline,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = _extract_message_content(
            result, model=settings.model_for_pipeline(pipeline), pipeline=pipeline
        )
        # Strip markdown code-fence wrappers the model may add
        content = re.sub(r"^```(?:json)?\s*\n?", "", content.strip())
        content = re.sub(r"\n?```\s*$", "", content.strip())
        return json.loads(content)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()


# Module-level singleton
llm_client = OpenRouterClient()
