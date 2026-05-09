# ADR 0004 — Langfuse for LLM Observability

**Date:** 2026-04-19  
**Status:** Accepted

## Context

Debugging and iterating on LLM pipelines is difficult without visibility into
prompts, completions, latencies, and costs. Standard application logging is
insufficient for structured LLM traces.

## Decision

Wrap every LLM call via `services/llm/tracing.py` which integrates
**Langfuse** (cloud-hosted). This is a hard convention enforced by code review and
documented in backend `CLAUDE.md`. No LLM call may bypass tracing.

## Consequences

- **+** Full prompt/completion history is available in the Langfuse dashboard for
  debugging and prompt engineering.
- **+** Token usage and cost tracking per pipeline out of the box.
- **+** Centralised place to attach user feedback scores (thumbs up/down) back to
  the originating LLM trace.
- **+** Tracing is opt-out at runtime: if `LANGFUSE_PUBLIC_KEY` is not set, the
  client is a no-op, so the app works in offline/dev mode.
- **−** Another third-party SaaS dependency; traces contain prompt data sent to
  Langfuse servers.
- **−** Developers must remember to route all LLM calls through the wrapper.
  Architecture tests enforce that only `services/llm/client.py` is imported for
  LLM calls (import-level check), but call-path correctness still relies on
  convention and review.
