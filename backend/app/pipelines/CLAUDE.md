# Pipelines — AI Coding Instructions

## Purpose
Batch orchestrators for scheduled processing.  Pipelines coordinate service calls, LLM interactions, and data flow for the nightly/weekly cycles.

## Conventions
- Each pipeline file has a top-level `async def run_*()` function.
- All wrap their work in a `ProcessingLog` entry (started → completed/failed).
- Blocking triage check: `profile_update` aborts if high/critical triage items are unresolved.
- LLM calls use `llm_client` + `trace_llm_call` for observability.
- Pipelines commit their own DB changes (they own the session lifecycle).
- Each pipeline exposes a top-level `async def run_*()` coroutine; callers `await` it directly. Pipelines run on schedule via cron — there is no admin API or CLI entrypoint.

## Pipeline files
- `profile_update.py` — nightly: topic extraction + profile update
- `quiz_pipeline.py` — nightly: quiz generation + evaluation
- `reading_pipeline.py` — weekly: reading recommendation generation
- `project_pipeline.py` — weekly: Go practice project generation + evaluation

## Error handling
Pipelines catch exceptions, record them in `ProcessingLog.error`, and set status to `failed`.  They do **not** re-raise — callers (cron) should check logs.

## Gotchas
- `project_pipeline.py` validates that the generated Go code compiles (`go build`). On failure it retries generation (up to a fixed limit) before recording a failed log.
