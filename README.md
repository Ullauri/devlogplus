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
| Database | PostgreSQL 18 with pgvector |
| LLM | OpenRouter (Claude Sonnet default) |
| Observability | Langfuse |
| Testing | pytest, pytest-bdd, Vitest, Testing Library |
| Linting | Ruff (backend), ESLint (frontend) |

## Prerequisites

DevLog+ is designed to run **natively** for real use. Running the app needs no Docker at all; the Compose stack is only a convenience for local development (see [Docker Compose stack](#docker-compose-stack)). Running the **backend test suite** is the one exception — it requires a Docker daemon, because the tests spin up a throwaway Postgres with testcontainers.

- Python 3.12+
- Node.js 20+
- PostgreSQL 16+ with the [pgvector](https://github.com/pgvector/pgvector) extension installed and available to the server — but on Homebrew use 17 or 18, because 16 has no pgvector build there (see [step 1](#1-install-postgresql-18-with-pgvector))
- A Postgres role with privileges to `CREATE EXTENSION vector` (superuser is simplest; the extension is enabled by the initial migration)
- An [OpenRouter](https://openrouter.ai/) API key
- A Docker daemon **only if you plan to run the backend tests** — see [Running the tests](#running-the-tests)

## Quick Start (native)

This is the intended way to run DevLog+ for real use.

### 1. Install PostgreSQL 18 with pgvector

You need both Postgres 18 **and** the `pgvector` extension package installed on the host. The extension itself is enabled automatically by the first migration (`CREATE EXTENSION IF NOT EXISTS vector`), but the shared library must already be available to the server.

> **On macOS, do not use Postgres 16.** As of pgvector 0.8.6 the Homebrew bottle ships `vector.dylib` for `postgresql@17` and `postgresql@18` only, so on 16 the first migration dies on `extension "vector" is not available` — which reads like a missing package, and reinstalling `pgvector` changes nothing. Check your own bottle with `ls $(brew --prefix)/opt/pgvector/lib/*/` — one `vector.dylib` per supported major. This is a **host install** constraint only: the `pgvector/pgvector` images used by the Compose stack and the test suite ship the extension prebuilt, which is why they can stay on pg16. On Debian/Ubuntu, PGDG packages pgvector for every supported major, so 16 works there — 18 is simply what this setup is verified against.

```bash
# Debian / Ubuntu — Postgres 18 is not in the distro repos, so add PGDG first.
# See https://www.postgresql.org/download/linux/ubuntu/
sudo apt install -y postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh
sudo apt install postgresql-18 postgresql-18-pgvector
```

```bash
# macOS (Homebrew)
brew install postgresql@18 pgvector
brew services start postgresql@18

# postgresql@18 is keg-only: psql, createdb, createuser and pg_dump are NOT on
# PATH until you add them, and both `make migrate` and `make run` need pg_dump.
# Persist it, then apply it to this shell too (Intel Macs: /usr/local/opt/...):
echo 'export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"' >> ~/.zshrc
export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"
```

Other platforms: see https://github.com/pgvector/pgvector#installation

Create the database and role referenced by the default `DATABASE_URL`:

```bash
# Debian / Ubuntu — the package creates a `postgres` system user
sudo -u postgres createuser -s devlogplus            # superuser simplifies CREATE EXTENSION
sudo -u postgres createdb -O devlogplus devlogplus
sudo -u postgres psql -c "ALTER USER devlogplus WITH PASSWORD 'devlogplus';"
```

```bash
# macOS (Homebrew) — there is no `postgres` system user; the install makes your
# own macOS account a superuser role, so run these directly
createuser -s devlogplus
createdb -O devlogplus devlogplus
psql -d postgres -c "ALTER USER devlogplus WITH PASSWORD 'devlogplus';"
```

> If you prefer a non-superuser role, run `CREATE EXTENSION vector;` once manually as a superuser against the `devlogplus` database before `make migrate`.

### 2. Install project dependencies

```bash
make venv
source .venv/bin/activate
```

This creates `.venv/` and installs both backend (Python) and frontend (npm) dependencies.

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

To run the test suite, see [Running the tests](#running-the-tests) — the backend tests additionally need a Docker daemon.

### Troubleshooting

- `extension "vector" is not available` — on macOS this is usually a **version mismatch**, not a missing package: Homebrew's `pgvector` has no build for your Postgres major (see [step 1](#1-install-postgresql-18-with-pgvector)). Otherwise the `pgvector` package isn't installed on the host. Either way, install the right one and restart Postgres (`brew services restart postgresql@18`).
- `permission denied to create extension "vector"` — the `devlogplus` role isn't a superuser. Either grant superuser, or run `CREATE EXTENSION vector;` manually as a superuser before migrating.
- `could not translate host name "db"` — you're still using the Docker-style `DATABASE_URL`; change `@db:` to `@localhost:` in `.env`.

## Development

### Running the tests

The backend suite uses [testcontainers](https://testcontainers.com/), which starts a throwaway Postgres container for the test session. **A running Docker daemon is therefore required for `make test` and `make test-backend`** — the one place the "Docker is only a convenience" rule does not hold. Without a daemon the tests do not skip; they error in bulk, and the output reads like a broken checkout rather than a missing prerequisite.

```bash
make test            # backend + frontend
make test-backend    # backend only — needs Docker
make test-bdd        # Gherkin BDD subset — needs Docker (same Postgres fixture)
make test-frontend   # frontend only — no Docker needed
make test-arch       # architecture rules — needs Docker (one ORM test hits the DB)
```

#### Using colima (macOS)

[colima](https://github.com/abiosoft/colima) works as the daemon, but needs two environment variables that Docker Desktop would make unnecessary:

```bash
brew install colima docker docker-compose
colima start

# Persist them, then apply them to this shell too
echo 'export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"' >> ~/.zshrc
echo 'export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock' >> ~/.zshrc
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock
```

Both are required, and setting only the first gets you a working `docker` CLI alongside a still-failing test suite — which is the confusing half:

- **`DOCKER_HOST`** — the `docker` CLI finds the daemon through its own context (`~/.docker/config.json`), but Python's Docker SDK does not read contexts; it falls back to `/var/run/docker.sock`, which colima never creates on the host. Symptom: `docker.errors.DockerException: Error while fetching server API version ... FileNotFoundError`.
- **`TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE`** — the path testcontainers mounts *inside* the VM for its Ryuk reaper, where the socket does sit in the conventional place. Symptom: `docker.errors.APIError: 500 ... mkdir /Users/<you>/.colima/default/docker.sock: operation not supported`, naming a path that plainly exists.

### Docker Compose stack

For local development, a Docker Compose stack is provided that runs Postgres (with pgvector preinstalled) and the backend with hot-reload. **This stack is a development convenience only** — production/real runs should use the native path above. It is separate from the Docker requirement for the tests described above.

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

# Run all tests (backend tests need Docker — see "Running the tests" above)
make test

# Run only backend / frontend tests
make test-backend
make test-frontend

# Run BDD tests (also needs Docker)
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
