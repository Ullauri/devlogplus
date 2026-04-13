# Backend — AI Coding Instructions

## Overview
This is the FastAPI backend for DevLog+.  It is an **async** Python 3.12+ application using SQLAlchemy 2.0 (async), Pydantic v2, and PostgreSQL 16 with pgvector.

## Package layout
```
backend/
  app/
    config.py       — pydantic-settings, loads from .env
    database.py     — async engine + session factory
    main.py         — FastAPI app, lifespan, routers, static files
    models/         — SQLAlchemy ORM models
    schemas/        — Pydantic request/response schemas
    routers/        — FastAPI route handlers (thin — delegate to services)
    services/       — Business logic + LLM integration
      llm/          — OpenRouter client, Langfuse tracing, structured output models
    prompts/        — Version-controlled LLM prompt constants
    pipelines/      — Batch pipeline orchestrators (nightly/weekly)
  migrations/       — Alembic async migrations
  tests/            — pytest-asyncio test suite
```

## Key conventions
- **Async everywhere**: all DB calls use `await`, all services are `async def`.
- **Dependency injection**: use FastAPI `Depends(get_db)` for sessions.
- **Pydantic v2 schemas**: separate Create / Update / Response models per entity.
- **Thin routers**: routers only parse requests and call services — no business logic.
- **LLM prompt isolation**: prompts live in `prompts/*.py` as constants, never inline in services/pipelines.
- **Langfuse tracing**: every LLM call must be wrapped via `services/llm/tracing.py`.
- **UUID primary keys**: all models inherit `UUIDMixin` which auto-generates `uuid4` PKs.
- **Timestamp columns**: all models inherit `TimestampMixin` — `created_at` / `updated_at` with server defaults.
- **JSONB for flexible data**: evidence_summary, metadata, LLM raw outputs, etc.
- **pgvector**: 1536-dim embeddings on journal_entry_versions and topics.

## Running
```bash
poetry install          # install deps
poetry run uvicorn backend.app.main:app --reload  # local dev
docker compose up       # full stack
```

## Testing
```bash
poetry run pytest backend/tests -v
```
