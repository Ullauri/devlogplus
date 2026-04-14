"""OpenRouter LLM client — single integration point for all LLM calls."""

import json
import logging
import re
from typing import Any

import httpx

from backend.app.config import settings
from backend.app.services.llm.tracing import trace_llm_call

logger = logging.getLogger(__name__)


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

        # Trace through Langfuse
        with trace_llm_call(
            pipeline=pipeline,
            model=model,
            input_data={"messages": messages},
        ) as trace:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
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
        return result["choices"][0]["message"]["content"]

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
        content = result["choices"][0]["message"]["content"]
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
