# DevLog+

A single-user, self-hosted developer journal for technical learning and skill maintenance. DevLog+ combines an AI-powered **Learning Engine** that builds a visible knowledge profile from your journal entries with a **Practice Engine** that generates weekly micro-projects to keep your hands-on skills sharp.

## Features

### Learn
- **Technical journal** — capture reflections via text or browser speech-to-text; edits are versioned automatically
- **Knowledge Profile** — AI-derived map of your strengths, weak spots, current frontier, and next frontier, updated nightly
- **Reading recommendations** — curated from your allowlisted domains, targeted to gaps and growth areas

### Practice
- **Weekly quizzes** — free-text questions that probe understanding; answers evaluated by LLM for correctness, depth, and confidence
- **Weekly micro-projects** — generated Go projects with starter code, tests, and tasks (bugs, features, refactors); submit for automated evaluation

### Manage
- **Feedback & feedforward** — thumbs-up/down reactions correct the system; free-text notes shape what it generates next
- **Triage queue** — surfaces items the system can't confidently resolve for your review, with severity levels
- **Data transfer** — export all data to a single JSON file and import it on another machine to pick up where you left off
- **Onboarding** — guided first-run experience (~10–15 min) that establishes your baseline before the learning cycle begins
- **Settings** — configure models, schedules, and allowlisted domains from the UI or environment variables

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Pydantic |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Database | PostgreSQL 16 with pgvector |
| LLM | OpenRouter (Claude Sonnet default) |
| Observability | Langfuse |
| Testing | pytest, pytest-bdd, Vitest, Testing Library |
| Linting | Ruff (backend), ESLint (frontend) |

## Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16 with the [pgvector](https://github.com/pgvector/pgvector) extension (or Docker)
- An [OpenRouter](https://openrouter.ai/) API key

## Quick Start

### 1. Clone and set up the environment

```bash
make venv
source .venv-devlogplus/bin/activate
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql+asyncpg://devlogplus:devlogplus@localhost:5432/devlogplus
OPENROUTER_API_KEY=your-key-here

# Optional
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 3a. Run natively

```bash
make run
```

This builds the frontend, runs database migrations, and starts the server at **http://localhost:8000**.

### 3b. Run with Docker (development)

```bash
make up
make migrate-docker
```

The app is available at **http://localhost:8000** with hot-reload enabled.

## Development

```bash
# Backend dev server with hot-reload
make dev

# Frontend dev server with Prism mock API (no backend needed)
make dev-mock

# Lint and auto-fix
make lint

# Run all tests
make test

# Run only backend / frontend tests
make test-backend
make test-frontend

# Run BDD tests
make test-bdd

# Run architecture tests
make test-arch

# Database migrations
make migrate

# Export OpenAPI spec
make openapi
```

Run `make help` to see all available targets.

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI entry point
│   │   ├── config.py         # Settings from environment
│   │   ├── database.py       # Async SQLAlchemy setup
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── routers/          # API route handlers
│   │   ├── services/         # Business logic & LLM client
│   │   ├── pipelines/        # LLM pipeline orchestration
│   │   └── prompts/          # LLM prompt templates
│   ├── migrations/            # Alembic database migrations
│   ├── scripts/               # Evaluation scripts
│   └── tests/                 # Backend test suite
├── frontend/
│   └── src/                   # React + TypeScript application
├── docs/
│   ├── PRD.md                 # Product requirements
│   └── openapi.json           # Generated OpenAPI spec
├── workspace/
│   └── projects/              # Generated project files
├── scripts/                   # Utility scripts (backup, cron)
├── docker-compose.yml         # Dev Docker setup (app + pgvector)
├── Dockerfile                 # Multi-stage build (dev & prod)
├── Makefile                   # All dev/build/test commands
└── pyproject.toml             # Python dependencies & tooling config
```

## LLM Node Evaluations

Evaluation scripts measure accuracy and latency of individual LLM pipeline nodes against OpenRouter. **These cost real money** — run them explicitly:

```bash
make eval                  # All node evals (default 3 iterations)
make eval ITERS=5          # All node evals, 5 iterations
make eval-topic-extraction # Single node eval
```
