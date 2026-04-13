"""Shared test fixtures for DevLog+ backend tests.

Uses testcontainers to spin up a real PostgreSQL container for the test session
and tears it down automatically when tests finish.

All async fixtures and tests share a single session-scoped event loop to avoid
asyncpg "attached to a different loop" errors.
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from backend.app.database import get_db
from backend.app.main import app
from backend.app.models import Base

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
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine(test_database_url: str):
    """Create a test database engine and install schema once for the session."""
    engine = create_async_engine(test_database_url, echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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
