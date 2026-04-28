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
Postgres instance that may be local or running via `docker-compose`. The Docker
image is for production-style runs (`make run`) and CI. Frontend dev always runs
natively via Vite (`npm run dev` or `npm run dev:mock`).

The virtualenv is managed under `.venv-devlogplus/` and pinned via
`pyproject.toml`. `make venv` creates and fully populates it.

## Consequences

- **+** Hot-reload (`uvicorn --reload`) is instant without container
  layer overhead.
- **+** No Docker socket dependency for the common development workflow.
- **+** Debugger attach and `pdb` work without extra container configuration.
- **−** Developers must have Python 3.12+ and a compatible Postgres installed
  locally (or run `docker-compose up db` to get just the database).
- **−** "Works on my machine" risk — the Dockerfile pins the production
  environment, but local dependencies could drift. `pyproject.toml` lock file
  mitigates this.
