# Models — AI Coding Instructions

## Purpose
SQLAlchemy 2.0 declarative ORM models mapping to PostgreSQL tables.

## Conventions
- All models inherit from `Base` (declarative base) plus `UUIDMixin` and `TimestampMixin`.
- `UUIDMixin` provides `id: Mapped[uuid.UUID]` as a `uuid4` primary key.
- `TimestampMixin` provides `created_at` and `updated_at` with `server_default=func.now()`.
- Enums are defined in `base.py` as Python `enum.Enum` subclasses and stored as `Text` in Postgres (not native PG enums) for migration simplicity.
- Foreign keys use `postgresql.UUID(as_uuid=True)`.
- JSONB columns use `postgresql.JSONB` for flexible structured data.
- `Vector(1536)` from pgvector is used for embedding columns.
- Relationships use `back_populates` for bidirectional access.
- `__tablename__` is always set explicitly.

## Adding a model
1. Create the model class in the appropriate file (or a new file).
2. Re-export it from `__init__.py`.
3. Create an Alembic migration: `alembic revision --autogenerate -m "description"`.
