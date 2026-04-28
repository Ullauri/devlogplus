# ADR 0003 — PostgreSQL + pgvector for Embeddings

**Date:** 2026-04-19  
**Status:** Accepted

## Context

The application needs to store and query vector embeddings (1536-dim) for journal
entry versions and knowledge-profile topics — used for semantic similarity when
updating the profile and deduplicating topics.

Options considered:
1. Dedicated vector database (Pinecone, Weaviate, Qdrant) alongside PostgreSQL.
2. PostgreSQL 16 with the **pgvector** extension.

## Decision

Use **pgvector** inside the existing PostgreSQL 16 instance. Embeddings are stored
as `vector(1536)` columns on `journal_entry_versions` and `topics` tables.

## Consequences

- **+** No second data store to run, back up, or keep in sync.
- **+** Vector queries can be joined with relational data in a single SQL
  statement (e.g. find similar topics that also belong to a given user).
- **+** Alembic migrations handle schema evolution for both relational and vector
  columns uniformly.
- **+** JSONB + pgvector covers flexible storage needs without introducing NoSQL.
- **−** pgvector's ANN index (HNSW/IVFFlat) is less mature than dedicated vector
  databases at very large scale — acceptable for a personal app.
- **−** Requires pgvector to be installed in the Postgres image (handled in
  `docker-compose.yml`).
