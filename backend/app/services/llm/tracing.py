"""Langfuse tracing integration for LLM calls.

Every LLM call is traced through Langfuse for observability:
- Full request/response logging
- Latency and token usage tracking
- Trace grouping by pipeline
- Cost visibility across models
"""

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from backend.app.config import settings

logger = logging.getLogger(__name__)

# Lazy-initialized Langfuse client
_langfuse = None


def _get_langfuse():
    """Get or initialize the Langfuse client."""
    global _langfuse
    if _langfuse is None:
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            logger.warning("Langfuse keys not configured — tracing disabled")
            return None
        try:
            from langfuse import Langfuse

            _langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
        except Exception:
            logger.exception("Failed to initialize Langfuse client")
            return None
    return _langfuse


@dataclass
class LLMTrace:
    """Handle for recording LLM call results into Langfuse."""

    pipeline: str
    model: str
    input_data: dict[str, Any]
    start_time: float = field(default_factory=time.time)
    _generation: Any = field(default=None, repr=False)

    def record_output(self, result: dict[str, Any]) -> None:
        """Record the LLM response, token usage, and latency."""
        elapsed = time.time() - self.start_time

        usage = result.get("usage", {})
        logger.info(
            "LLM call [%s] model=%s tokens_in=%s tokens_out=%s latency=%.2fs",
            self.pipeline,
            self.model,
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            elapsed,
        )

        if self._generation is not None:
            try:
                self._generation.end(
                    output=result.get("choices", [{}])[0].get("message", {}),
                    usage={
                        "input": usage.get("prompt_tokens"),
                        "output": usage.get("completion_tokens"),
                        "total": usage.get("total_tokens"),
                    },
                    metadata={"latency_seconds": elapsed},
                )
            except Exception:
                logger.exception("Failed to end Langfuse generation")


@contextmanager
def trace_llm_call(
    *,
    pipeline: str,
    model: str,
    input_data: dict[str, Any],
) -> Generator[LLMTrace, None, None]:
    """Context manager that wraps an LLM call with Langfuse tracing.

    Usage::

        with trace_llm_call(pipeline="quiz_generation", model="...", input_data={...}) as trace:
            result = await client.post(...)
            trace.record_output(result)
    """
    langfuse = _get_langfuse()
    trace_obj = LLMTrace(pipeline=pipeline, model=model, input_data=input_data)

    if langfuse is not None:
        try:
            lf_trace = langfuse.trace(
                name=pipeline,
                metadata={"model": model},
            )
            trace_obj._generation = lf_trace.generation(
                name=f"{pipeline}_generation",
                model=model,
                input=input_data,
            )
        except Exception:
            logger.exception("Failed to start Langfuse trace")

    try:
        yield trace_obj
    finally:
        # Flush traces asynchronously (best-effort)
        if langfuse is not None:
            try:
                langfuse.flush()
            except Exception:
                logger.debug("Langfuse flush failed (non-critical)")
