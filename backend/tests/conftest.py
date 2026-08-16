"""Shared test fixtures for DevLog+ backend tests.

Uses testcontainers to spin up a real PostgreSQL container for the test session
and tears it down automatically when tests finish.

All async fixtures and tests share a single session-scoped event loop to avoid
asyncpg "attached to a different loop" errors.

Two autouse fixtures below seal the test process off from anything real: the
container replaces the configured database everywhere, not only where ``get_db``
is injected, and the LLM client refuses to make a call nobody patched. Both
guard the same blind spot — a ``BackgroundTasks`` pipeline run, which starts
after the response the test asserted on has already been returned.
"""

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from backend.app import database
from backend.app.database import get_db
from backend.app.main import app
from backend.app.models import Base
from backend.app.services.llm.client import llm_client

# ---------------------------------------------------------------------------
# All async tests in this directory use a single session-scoped event loop
# so they share the same asyncpg connections created by session-scoped fixtures.
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# PostgreSQL container (session-scoped, started once for the whole test run)
# ---------------------------------------------------------------------------
POSTGRES_IMAGE = "pgvector/pgvector:pg16"
POSTGRES_USER = "test"
POSTGRES_PASSWORD = "test"
POSTGRES_DB = "devlogplus_test"


@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL + pgvector container and yield it."""
    with PostgresContainer(
        image=POSTGRES_IMAGE,
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        dbname=POSTGRES_DB,
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def test_database_url(postgres_container) -> str:
    """Build an asyncpg connection string from the running container."""
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    return (
        f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}" f"@{host}:{port}/{POSTGRES_DB}"
    )


# ---------------------------------------------------------------------------
# Database engine & session factory (session-scoped)
# ---------------------------------------------------------------------------
# Project root: devlogplus/ — used to locate alembic.ini.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic_upgrade(sync_database_url: str) -> None:
    """Apply all Alembic migrations against the test DB.

    We use Alembic (not ``Base.metadata.create_all``) so the test schema is
    byte-for-byte identical to production. ``create_all`` auto-creates PG
    native enum types from ``Mapped[SomeEnum]`` columns, masking drift between
    models and migration files (see Apr 2026 ``UndefinedObjectError`` incident
    for ``quizsessionstatus`` / ``pipelinetype``).
    """
    cfg = AlembicConfig(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "backend" / "migrations"))
    # Alembic env.py runs the async engine itself; give it a sync-style URL
    # (asyncpg driver) via env var override.
    cfg.set_main_option("sqlalchemy.url", sync_database_url)
    alembic_command.upgrade(cfg, "head")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine(test_database_url: str):
    """Create a test database engine and install schema once for the session.

    Schema is applied via ``alembic upgrade head`` to match production exactly.
    """
    # Alembic's env.py reads ``settings.database_url``; override it so the
    # migration run targets the testcontainer, not the configured dev DB.
    from backend.app import config as _config

    original_url = _config.settings.database_url
    _config.settings.database_url = test_database_url
    try:
        # Alembic's env.py calls ``asyncio.run(...)`` internally, which fails
        # from inside a running loop — so run it on a worker thread.
        await asyncio.to_thread(_run_alembic_upgrade, test_database_url)
    finally:
        _config.settings.database_url = original_url

    engine = create_async_engine(test_database_url, echo=False)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP EXTENSION IF EXISTS vector"))
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_session_factory(test_engine):
    """Session factory bound to the test engine."""
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# ---------------------------------------------------------------------------
# Sealing the developer's real database off from the test run
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _seal_off_the_configured_database(test_engine, test_session_factory):
    """Point every un-injected session at the container, not at ``DATABASE_URL``.

    Overriding ``get_db`` only covers sessions the app asks a request for.
    Anything opening its own — a ``BackgroundTasks`` pipeline run, the MCP
    server — goes through ``database.session_scope``, which reads this module
    global. Left alone it points at the developer's real database, and the
    background half of a test writes there: 82 bogus ``project_evaluation``
    failures accumulated in one before this fixture existed.

    Autouse and session-scoped, because the leak is in code a test does not
    mention and would therefore never think to opt in to.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(database, "engine", test_engine)
        mp.setattr(database, "async_session_factory", test_session_factory)
        yield


@pytest.fixture(autouse=True)
def _no_real_llm_calls():
    """Refuse to reach OpenRouter, loudly, from anywhere in the suite.

    Tests that want an LLM response patch the client themselves, and those
    patches still win — this only catches the paths that arrive by accident.
    The one that matters runs inside a background task, after the assertions
    have already passed, so a real call there would bill the user's API key
    and still leave the test green.

    ``chat_completion`` is the only seam needed: ``chat_completion_text`` and
    ``chat_completion_json`` both funnel through it.
    """

    async def _refuse(*args, **kwargs):
        raise RuntimeError(
            "A test reached the real LLM client. Patch chat_completion (or the "
            "_text/_json wrapper the code under test calls) in the test itself."
        )

    with patch.object(llm_client, "chat_completion", new=_refuse):
        yield


# ---------------------------------------------------------------------------
# Per-test database session (with table truncation for isolation)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(loop_scope="session")
async def db_session(
    test_session_factory,
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh session per test; truncate all tables after each test."""
    async with test_session_factory() as session:
        yield session

    # Clean all user tables after each test for isolation
    async with test_session_factory() as cleanup_session:
        for table in reversed(Base.metadata.sorted_tables):
            await cleanup_session.execute(text(f"TRUNCATE {table.fullname} CASCADE"))
        await cleanup_session.commit()


# ---------------------------------------------------------------------------
# HTTP test client
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP test client with the DB session overridden."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
