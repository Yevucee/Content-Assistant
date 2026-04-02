"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """DATABASE_URL from environment with local SQLite default."""
    default = "sqlite+aiosqlite:///./data/harness.db"
    url = os.environ.get("DATABASE_URL", default)
    if "+asyncpg" in url or url.startswith("postgresql+asyncpg"):
        return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def get_engine():
    global _engine
    if _engine is None:
        url = get_database_url()
        # SQLite: default pool (unchanged local dev behaviour).
        # Postgres on Railway / PaaS: NullPool avoids holding idle connections that the
        # provider may close; reusing dead sockets from a QueuePool often surfaces as
        # asyncpg "connection is closed" on checkout or first use.
        if url.startswith("sqlite"):
            _engine = create_async_engine(
                url,
                echo=False,
                pool_pre_ping=True,
            )
        else:
            _engine = create_async_engine(
                url,
                echo=False,
                pool_pre_ping=True,
                poolclass=NullPool,
            )
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
