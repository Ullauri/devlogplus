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

## Coverage
There is one service module per domain entity (journal, profile, quiz, reading, project, triage, onboarding, feedback, transfer). New domains follow the same pattern — one file, exported via `__init__.py`. `ProcessingLog` outcomes (status, error, metadata) are written directly by pipelines, not wrapped in a service; creating the row goes through `pipelines.open_run_log` so a pipeline adopts the row its manual trigger reserved.

`pipelines.py` is a special-purpose helper for the pipeline-trigger router (run-status queries, run-id minting) and for the run-row lifecycle the router shares with the pipelines it launches (`reserve_run`, `open_run_log`, `fail_abandoned_run`) — not a domain entity service. It does not follow the standard CRUD pattern.
