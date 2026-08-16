# ADR 0007 — No Docker for Local Development (Native Python + Postgres)

**Date:** 2026-04-19  
**Status:** Accepted

## Context

A `Dockerfile` and `docker-compose.yml` exist in the repository. Running
everything inside Docker (backend + frontend + Postgres) is one option; running
the backend natively against a local/remote Postgres is another. Fast iteration
cycles matter for a solo project.

## Decision

Local development runs the **backend natively** (virtualenv, `make dev`) against a
Postgres instance that may be local or running via `docker-compose`. The
project's Docker image is built only by the optional Compose stack (`make up`,
`make down`, `make migrate-docker`); neither `make run` nor CI builds or uses
it. Frontend dev always runs natively via Vite (`npm run dev` or
`npm run dev:mock`).

The virtualenv is managed under `.venv/` and pinned via `pyproject.toml`.
`make venv` creates and fully populates it.

> **Amended 2026-08-07.** As originally written this said `.venv-devlogplus/`,
> and "fully populates it" was not true: `poetry install` ignored that venv and
> populated Poetry's cache venv instead, so activating the in-project one broke
> `poetry run`. The venv is now `./.venv` — the only path Poetry treats as
> in-project — with a committed `poetry.toml` covering the cases the rename
> alone does not. The decision this ADR records — native backend, no Docker for
> local dev — is unchanged.

> **Amended 2026-08-16.** Two descriptions of the tree were wrong as originally
> written, and both are corrected above and below. The Decision said "The Docker
> image is for production-style runs (`make run`) and CI." It is used by
> neither: `make run` builds the frontend, backs up, then runs `alembic` and
> `uvicorn` through Poetry, with no container anywhere — it *is* the native path
> this ADR argues for — and `.github/workflows/ci.yml` never builds or runs this
> project's image. CI does need a Docker **daemon**, but for the throwaway
> `pgvector` Postgres that testcontainers starts in the backend tests, which is
> a different image and a different claim. The Consequences called
> `pyproject.toml` a lock file; the lock file is `poetry.lock`. The decision is
> again unchanged — only its description of what Docker is for.

## Consequences

- **+** Hot-reload (`uvicorn --reload`) is instant without container
  layer overhead.
- **+** No Docker socket dependency for the common development workflow.
- **+** Debugger attach and `pdb` work without extra container configuration.
- **−** Developers must have Python 3.12+ and a compatible Postgres installed
  locally (or run `docker-compose up db` to get just the database).
- **−** "Works on my machine" risk — the Dockerfile pins the production
  environment, but local dependencies could drift. The committed `poetry.lock`
  mitigates this — `pyproject.toml` declares version constraints, not the
  resolved versions.
