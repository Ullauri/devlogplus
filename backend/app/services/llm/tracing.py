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

# ``.env`` is seeded from ``.env.example``, whose Langfuse values are
# ``your-langfuse-public-key-here``. An emptiness check passes those, so the
# app builds a client from them and every trace 401s in a background thread —
# invisibly, because the one warning that would say otherwise never fires.
# Matching the placeholder shape is what makes "never configured" detectable.
_PLACEHOLDER_PREFIX = "your-"
_PLACEHOLDER_SUFFIX = "-here"


def _is_placeholder(value: str) -> bool:
    """True for an ``.env.example`` stand-in that was never filled in.

    Deliberately narrow. Self-hosted Langfuse lets headless init mint keys in
    any shape, so this must not reject an unusual-but-real key — the startup
    check below is what catches those.
    """
    candidate = value.strip().lower()
    return candidate.startswith(_PLACEHOLDER_PREFIX) and candidate.endswith(_PLACEHOLDER_SUFFIX)


def tracing_configured() -> bool:
    """Whether usable-looking Langfuse credentials are present."""
    public, secret = settings.langfuse_public_key, settings.langfuse_secret_key
    if not public or not secret:
        return False
    return not (_is_placeholder(public) or _is_placeholder(secret))


def _get_langfuse():
    """Get or initialize the Langfuse client."""
    global _langfuse
    if _langfuse is None:
        if not tracing_configured():
            logger.warning(
                "Langfuse keys not configured — tracing disabled. Run 'make langfuse-up' for a "
                "local instance, or set LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY."
            )
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


def verify_tracing() -> str:
    """Check credentials once, and say plainly which of the three states we're in.

    Traces are written from a background thread that swallows its own HTTP
    failures, so a bad key or a region mismatch is silent for the life of the
    process — the symptom is an empty dashboard noticed days later. Calling
    ``auth_check`` once at startup converts that into a single log line.

    Never raises: tracing is optional, and losing observability must not stop
    the app from serving.
    """
    if not tracing_configured():
        logger.warning(
            "Langfuse tracing disabled — no credentials configured. LLM calls will run "
            "untraced, so failed responses leave no recoverable request body."
        )
        return "disabled"

    client = _get_langfuse()
    if client is None:
        return "disabled"

    try:
        client.auth_check()
    except Exception as exc:
        # Overwhelmingly a wrong host for the key's region: Langfuse Cloud
        # issues per-region keys, and one region's key is a 401 at the other's
        # hostname — which reads identically to a revoked key.
        logger.warning(
            "Langfuse credentials rejected by %s — tracing is effectively off (%s). Check the "
            "key pair, and that the host matches the region the project lives in.",
            settings.langfuse_host,
            exc,
        )
        return "unauthorized"

    logger.info("Langfuse tracing active (host=%s)", settings.langfuse_host)
    return "ok"


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
