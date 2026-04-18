# DevLog+ — AI Coding Instructions

## What this is
Personal learning companion: daily journal → LLM pipelines → knowledge profile, quizzes, reading recommendations, and Go practice projects.

## Tech stack
- **Backend**: FastAPI (async), SQLAlchemy 2.0, PostgreSQL 16 + pgvector, Pydantic v2, Alembic
- **Frontend**: React 18 + TypeScript, Vite, Tailwind CSS
- **LLM**: OpenRouter (model-per-pipeline), Langfuse tracing
- **Test**: pytest-asyncio, pytest-bdd, vitest, Prism mock server

## First-time setup
```bash
cp .env.example .env   # fill in OPENROUTER_API_KEY at minimum
make venv              # create virtualenv + install all deps (backend + frontend)
make migrate           # apply DB migrations (requires running Postgres)
```

## Primary commands
```bash
make run              # build frontend + migrate + serve (production-style native run)
make dev              # backend hot-reload dev server (no Docker)
make dev-mock         # frontend against Prism mock — no backend needed
make test             # full test suite (backend + frontend)
make test-integration # frontend contract tests against Prism mock
make lint             # auto-fix lint (backend + frontend)
make eval             # run all LLM node evaluations (slow — hits real API)
make test-bdd         # BDD/Gherkin feature tests only
make test-arch        # architecture boundary tests only
make help             # full target list
```

## Architecture
Strict layered DAG enforced by architecture tests (`make test-arch`):
```
pipelines → services/llm + services + prompts + models + config
routers   → services + schemas
services  → models + schemas
```
Each layer has its own `CLAUDE.md`. Start there for layer-specific conventions.

## Gotchas
- `.github/copilot-instructions.md` is a symlink pointing to `CLAUDE.md` — intentional (GitHub Copilot reads from that path); don't replace `CLAUDE.md` with a symlink

## Key files
- `backend/app/main.py` — FastAPI app wiring
- `backend/app/config.py` — all env var definitions (mirrors `.env.example`)
- `docs/PRD.md` — product requirements (15 areas)
- `docs/openapi.json` — API contract (generated; source of truth for Prism)
- `Makefile` — all dev/test/eval/deploy commands
