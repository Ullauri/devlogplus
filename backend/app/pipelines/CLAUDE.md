# Pipelines — AI Coding Instructions

## Purpose
Batch orchestrators for scheduled processing.  Pipelines coordinate service calls, LLM interactions, and data flow for the nightly/weekly cycles.

## Conventions
- Each pipeline file has a top-level `async def run_*()` function.
- All wrap their work in a `ProcessingLog` entry (started → completed/failed).
- Blocking triage check: `profile_update` aborts if high/critical triage items are unresolved.
- LLM calls use `llm_client` + `trace_llm_call` for observability.
- Pipelines commit their own DB changes (they own the session lifecycle).
- Can be invoked via cron (`python -m backend.app.pipelines.<name>`) or the admin API.

## Error handling
Pipelines catch exceptions, record them in `ProcessingLog.error`, and set status to `failed`.  They do **not** re-raise — callers (cron) should check logs.
