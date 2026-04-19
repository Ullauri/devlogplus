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

DevLog+ is designed to run **natively** for real use. Docker is only provided as a convenience for local development (see [Development](#development)).

- Python 3.12+
- Node.js 20+
- PostgreSQL 16 with the [pgvector](https://github.com/pgvector/pgvector) extension installed and available to the server
- A Postgres role with privileges to `CREATE EXTENSION vector` (superuser is simplest; the extension is enabled by the initial migration)
- An [OpenRouter](https://openrouter.ai/) API key

## Quick Start (native)

This is the intended way to run DevLog+ for real use.

### 1. Install PostgreSQL 16 with pgvector

You need both Postgres 16 **and** the `pgvector` extension package installed on the host. The extension itself is enabled automatically by the first migration (`CREATE EXTENSION IF NOT EXISTS vector`), but the shared library must already be available to the server.

```bash
# Debian / Ubuntu
sudo apt install postgresql-16 postgresql-16-pgvector

# macOS (Homebrew)
brew install postgresql@16 pgvector

# Other platforms: see https://github.com/pgvector/pgvector#installation
```

Create the database and role referenced by the default `DATABASE_URL`:

```bash
sudo -u postgres createuser -s devlogplus            # superuser simplifies CREATE EXTENSION
sudo -u postgres createdb -O devlogplus devlogplus
sudo -u postgres psql -c "ALTER USER devlogplus WITH PASSWORD 'devlogplus';"
```

> If you prefer a non-superuser role, run `CREATE EXTENSION vector;` once manually as a superuser against the `devlogplus` database before `make migrate`.

### 2. Install project dependencies

```bash
make venv
source .venv-devlogplus/bin/activate
```

This creates `.venv-devlogplus/` and installs both backend (Python) and frontend (npm) dependencies.

### 3. Configure environment variables

```bash
cp .env.example .env
```

Then edit `.env`:

- Set `OPENROUTER_API_KEY` (required).
- Change `DATABASE_URL` host from `@db:` to `@localhost:` (the shipped default targets the Docker compose service name):

  ```env
  DATABASE_URL=postgresql+asyncpg://devlogplus:devlogplus@localhost:5432/devlogplus
  ```
- Optionally fill in Langfuse keys for LLM tracing.

### 4. Run migrations and start the server

```bash
make migrate   # requires Postgres to be running and reachable
make run       # builds the frontend, applies migrations, and serves on :8000
```

Open **http://localhost:8000** for the UI, or **http://localhost:8000/docs** for the API.

### Troubleshooting

- `extension "vector" is not available` — the `pgvector` package isn't installed on the Postgres host. Install it (see step 1) and restart Postgres.
- `permission denied to create extension "vector"` — the `devlogplus` role isn't a superuser. Either grant superuser, or run `CREATE EXTENSION vector;` manually as a superuser before migrating.
- `could not translate host name "db"` — you're still using the Docker-style `DATABASE_URL`; change `@db:` to `@localhost:` in `.env`.

## Development

For local development, a Docker Compose stack is provided that runs Postgres (with pgvector preinstalled) and the backend with hot-reload. **Docker is intended for development only** — production/real runs should use the native path above.

```bash
make up                # start app + pgvector in Docker
make migrate-docker    # run migrations inside the container
make down              # stop the stack
```

Other common tasks:

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
