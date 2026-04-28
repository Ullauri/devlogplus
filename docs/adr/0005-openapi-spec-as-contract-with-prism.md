# ADR 0005 — OpenAPI Spec as Single Source of Truth (Prism Contract Testing)

**Date:** 2026-04-19  
**Status:** Accepted

## Context

The frontend `api/client.ts` and the backend FastAPI routers must stay in sync.
Without a contract mechanism, it is easy for the frontend to call endpoints that
no longer match the backend's expected shapes, or for the backend to change a
response schema without the frontend noticing until runtime.

## Decision

Treat `docs/openapi.json` (generated from FastAPI via `make openapi`) as the
**single source of truth** for the API contract. The contract is enforced at two
levels:

1. **Type generation**: `make openapi` regenerates `src/api/schema.gen.ts` from
   the spec. All request/response types in `client.ts` must come from this
   generated file — an architecture test enforces this.
2. **Integration tests**: [Stoplight Prism](https://github.com/stoplightio/prism)
   serves a mock API from the spec. Frontend integration tests run against Prism,
   verifying the real client-side HTTP calls match the spec.
3. **Pre-commit hook** (`openapi-regen`): auto-regenerates spec and TS types
   whenever backend router, schema, or `main.py` files change. `make openapi-check`
   fails CI if either file is stale.

## Consequences

- **+** Client↔server drift is caught at test/lint time, not in production.
- **+** Frontend development can proceed against the mock without a running
  backend (`make dev-mock`).
- **+** A single `make openapi` command keeps everything in sync.
- **−** Adds Prism as a dev/test dependency.
- **−** The pre-commit hook adds latency to commits touching backend routes.
- **−** Hand-rolled inline types in `client.ts` will cause the architecture test
  to fail — developers must always derive types from `schema.gen.ts`.
