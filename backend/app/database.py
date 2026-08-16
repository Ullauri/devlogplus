"""Async database engine, session factory, and dependency."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=(settings.app_env == "development"),
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with session_scope() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session for work that has no request to hang ``get_db`` off.

    Background tasks and the MCP server open their own sessions. They must do
    it through here rather than by importing ``async_session_factory``
    directly, because a module-level ``from ... import async_session_factory``
    binds the factory at import time and so puts that session beyond the reach
    of anything that swaps it afterwards.

    That is not hypothetical. The test suite overrides ``get_db`` to point at
    a throwaway container, but the override cannot reach a factory another
    module already captured — so the background half of every pipeline-trigger
    test ran against whatever ``DATABASE_URL`` named, which on a developer
    machine is the real database. It logged 82 failed ``project_evaluation``
    runs there, one pair per ``pytest`` invocation, each naming a project id
    that only ever existed in a container that had since been thrown away.
    Resolving the factory here, at call time, is what makes it swappable.
    """
    async with async_session_factory() as session:
        yield session
