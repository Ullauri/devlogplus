# Services — AI Coding Instructions

## Purpose
Business logic layer.  Services are async functions that take a DB session (and other params) and return domain objects or raise exceptions.

## Conventions
- All functions are `async def`.
- Functions accept `AsyncSession` as the first parameter (no global state).
- Keep functions focused — one concern per function.
- Services never import from `routers/` — the dependency flows routers → services → models.
- LLM calls go through `services/llm/client.py`, never directly via httpx.
- Prompt text is imported from `prompts/`, never hardcoded here.

## Sub-packages
- `llm/` — OpenRouter client, Langfuse tracing utilities, structured LLM output models.
