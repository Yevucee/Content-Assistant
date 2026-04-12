"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy import text
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


async def _repair_pipeline_runs_timestamptz(async_conn) -> None:
    """
    Hosted Postgres: older DBs may have TIMESTAMP WITHOUT TIME ZONE on audit columns while
    the ORM sends timezone-aware datetimes (asyncpg then raises naive/aware errors).

    If information_schema shows ``timestamp without time zone`` for created_at or updated_at,
    alter those columns to ``timestamptz``, interpreting existing naive values as UTC.
    New databases already get TIMESTAMPTZ from metadata.create_all and no-op here.
    """
    r = await async_conn.execute(
        text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'pipeline_runs'
              AND column_name IN ('created_at', 'updated_at')
            """
        )
    )
    rows = {row[0]: row[1] for row in r.fetchall()}
    if len(rows) < 2:
        return
    for col in ("created_at", "updated_at"):
        if rows.get(col) != "timestamp without time zone":
            continue
        await async_conn.execute(
            text(
                f"ALTER TABLE pipeline_runs ALTER COLUMN {col} TYPE timestamptz "
                f"USING {col} AT TIME ZONE 'UTC'"
            )
        )


async def init_db() -> None:
    """Create tables if missing (v1; replace with Alembic later)."""
    from harness.models.artifacts import RunSourceItem, RunTopicCandidate  # noqa: F401
    from harness.models.generated import RunGeneratedContent  # noqa: F401
    from harness.models.run import PipelineRun  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    url = get_database_url()
    if url.startswith("postgresql"):
        async with engine.begin() as conn:
            await _repair_pipeline_runs_timestamptz(conn)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one session per request."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
