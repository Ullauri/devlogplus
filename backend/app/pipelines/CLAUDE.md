# Pipelines — AI Coding Instructions

## Purpose
Batch orchestrators.  Pipelines coordinate service calls, LLM interactions, and data flow for the long-running generation and evaluation cycles.  Nothing schedules them — a pipeline runs because a user pressed a button.

## Conventions
- Each pipeline file has a top-level `async def run_*()` function.
- All wrap their work in a `ProcessingLog` entry (started → completed/failed).
- Blocking triage check: `profile_update` aborts if high/critical triage items are unresolved.
- LLM calls use `llm_client` + `trace_llm_call` for observability.
- Pipelines commit their own DB changes (they own the session lifecycle).
- Each pipeline exposes a top-level `async def run_*()` coroutine; callers `await` it directly. The only caller is `routers.pipelines`, which queues it as a FastAPI background task — there is no scheduler and no CLI entrypoint.

## Pipeline files
- `profile_update.py` — topic extraction + profile update
- `quiz_pipeline.py` — quiz generation + evaluation
- `reading_pipeline.py` — reading recommendation generation
- `project_pipeline.py` — Go practice project generation + evaluation

## Error handling
Pipelines catch exceptions, record them in `ProcessingLog.error`, and set status to `failed`.  They do **not** re-raise — a run is queued as a background task after the HTTP response has already gone out, so the log is the only place a failure surfaces.

## Gotchas
- `project_pipeline.py` validates that the generated Go code compiles (`go build`). On failure it retries generation (up to a fixed limit) before recording a failed log.
- `reading_pipeline.py` does **not** ask the LLM for URLs. The model has no web
  access and inventing plausible slugs is its default failure (14 straight 404s
  across two batches that stored nothing). It instead reads each allowlisted
  domain's RSS/Atom feed, offers the articles as a numbered pool, and the model
  returns `candidate_id`; title and URL come from the pool, never the response.
  Consequences worth knowing:
  - The pipeline makes real network calls to ~69 domains before the LLM call.
    Tests must stub `reading_svc.gather_candidates` or set
    `reading_use_feed_candidates=False`, or they will hit the internet and land
    in selection mode, where a URL-carrying stub response is correctly discarded.
  - Discovered feed URLs are cached on `reading_allowlist`, negatives included.
  - With no reachable feeds it falls back to model recall. That path still works
    but is the one that produces 404s, so `source_mode` is recorded on the run.
