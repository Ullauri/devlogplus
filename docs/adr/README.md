# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for DevLog+.

Each ADR documents a significant architectural or tooling decision: the context
that motivated it, the decision made, and the trade-offs accepted.

## Format

```
# ADR NNNN — Title

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Deprecated | Superseded by [NNNN]

## Context
## Decision
## Consequences
```

## Index

| # | Title | Status |
|---|-------|--------|
| [0001](0001-layered-architecture-with-test-enforcement.md) | Layered architecture with test enforcement | Accepted |
| [0002](0002-openrouter-as-llm-gateway.md) | OpenRouter as LLM gateway | Accepted |
| [0003](0003-postgresql-pgvector-for-embeddings.md) | PostgreSQL + pgvector for embeddings | Accepted |
| [0004](0004-langfuse-for-llm-observability.md) | Langfuse for LLM observability | Accepted |
| [0005](0005-openapi-spec-as-contract-with-prism.md) | OpenAPI spec as single source of truth (Prism contract testing) | Accepted |
| [0006](0006-bdd-gherkin-for-scenario-tests.md) | BDD / Gherkin for end-to-end scenario tests | Accepted |
| [0007](0007-native-dev-no-docker.md) | Native development, no Docker for local dev loop | Accepted |
