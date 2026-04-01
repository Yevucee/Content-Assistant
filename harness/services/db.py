"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """DATABASE_URL from environment with local SQLite default."""
    return os.environ.get(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./data/harness.db",
    )


def get_engine():
    global _engine
    if _engine is None:
        url = get_database_url()
        _engine = create_async_engine(url, echo=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def init_db() -> None:
    """Create tables if missing (v1; replace with Alembic later)."""
    from harness.models.artifacts import RunSourceItem, RunTopicCandidate  # noqa: F401
    from harness.models.generated import RunGeneratedContent  # noqa: F401
    from harness.models.run import PipelineRun  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one session per request."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Context manager helper for scripts."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
