# Migrations — AI Coding Instructions

## Purpose
Alembic database migrations for PostgreSQL.  Uses **async** engine (asyncpg).

## Key files
- `env.py` — async migration environment; reads DB URL from app config.
- `script.py.mako` — template for new migration files.
- `versions/` — numbered migration scripts.

## Commands
```bash
# Preferred (from project root) — auto-creates DB backup first:
make migrate

# Direct (with poetry run) — no automatic backup:
alembic downgrade -1           # Roll back one migration
alembic revision --autogenerate -m "description"  # Generate from model changes
```

## Notes
- The initial migration (001) enables the `vector` extension for pgvector.
- Enum values are stored as `Text`, not native PG enums — makes adding values trivial.
- Always test both upgrade and downgrade paths before committing.
