# ADR 0001 — Layered Architecture with Test Enforcement

**Date:** 2026-04-19  
**Status:** Accepted

## Context

As the application grew to include pipelines, services, routers, models, schemas,
and prompts, there was a risk of import cycles and cross-cutting concerns bleeding
across layers (e.g. a router importing a pipeline, or a service importing a
router). In a solo project, without discipline these boundaries erode quickly.

## Decision

Adopt a strict layered DAG and enforce it with automated architecture tests
(`make test-arch` via `tests/test_architecture.py`). The allowed import graph is:

```
pipelines → services/llm + services + prompts + models + config
routers   → services + schemas
services  → models + schemas
```

No upward imports are permitted. Violations are caught at test time, not at
code-review time.

## Consequences

- **+** Import cycles are structurally impossible if tests are green.
- **+** Each layer has a well-defined single responsibility, making the codebase
  navigable for AI coding assistants and future contributors.
- **+** Prompts are isolated in their own layer, making A/B testing and versioning
  of prompts straightforward.
- **−** Adds a small overhead when adding new cross-cutting helpers — they must be
  placed carefully to avoid violating the DAG.
- **−** Architecture tests must be kept up to date when new layers/modules are
  added.
