# Schemas — AI Coding Instructions

## Purpose
Pydantic v2 models for API request/response serialization and validation.

## Conventions
- **Three-schema pattern**: `EntityCreate` (input), `EntityUpdate` (partial update), `EntityResponse` (output). Not every entity needs all three.
- All schemas use `model_config = ConfigDict(from_attributes=True)` so they can be constructed directly from SQLAlchemy model instances.
- Complex responses use nested schemas (e.g., `JournalEntryDetail` embeds a list of `JournalEntryVersionResponse`).
- Use `Optional[...]` or `... | None` for nullable fields.
- `datetime` fields are always timezone-aware.
- `UUID` fields use Python's `uuid.UUID` — Pydantic serializes them to strings automatically.
- Pagination wrapper: `PaginatedResponse[T]` in `common.py`.

## File layout
Each file maps roughly to one domain entity. `common.py` has shared base schemas. `__init__.py` re-exports all public schema classes.

## Adding a schema
1. Define the schema class in the relevant file (or a new one).
2. Re-export it from `__init__.py`.
