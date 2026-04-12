"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

log = structlog.get_logger(__name__)

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


async def _repair_postgres_timestamp_columns(async_conn, *, app_tables: tuple[str, ...]) -> None:
    """
    Postgres only: legacy DBs may have ``timestamp without time zone`` while the app uses
    timezone-aware datetimes (asyncpg then raises naive/aware errors).

    Scope: ``public`` schema, only tables registered on ``SQLModel.metadata`` for this app
    (passed in as ``app_tables``). For each such column with type
    ``timestamp without time zone``, run ``ALTER … TYPE timestamptz`` interpreting stored
    naive instants as UTC.
    """
    log.info(
        "db.postgres_ts_repair.inspect_start",
        schema="public",
        app_tables=list(app_tables),
    )
    if not app_tables:
        log.warning("db.postgres_ts_repair.no_tables")
        return

    in_list = ", ".join(f"'{name}'" for name in app_tables)
    r = await async_conn.execute(
        text(
            f"""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN ({in_list})
              AND data_type IN (
                'timestamp without time zone',
                'timestamp with time zone'
              )
            ORDER BY table_name, ordinal_position
            """
        )
    )
    inspected = [(row[0], row[1], row[2]) for row in r.fetchall()]
    log.info(
        "db.postgres_ts_repair.inspect_columns",
        columns=[{"table": t, "column": c, "data_type": dt} for t, c, dt in inspected],
    )

    altered: list[dict[str, str]] = []
    for table_name, column_name, data_type in inspected:
        if data_type != "timestamp without time zone":
            continue
        stmt = (
            f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" TYPE timestamptz '
            f'USING "{column_name}" AT TIME ZONE \'UTC\''
        )
        try:
            await async_conn.execute(text(stmt))
            altered.append({"table": table_name, "column": column_name})
            log.info(
                "db.postgres_ts_repair.altered",
                table=table_name,
                column=column_name,
            )
        except Exception:
            log.exception(
                "db.postgres_ts_repair.alter_failed",
                table=table_name,
                column=column_name,
                statement=stmt,
            )
            raise

    if not altered:
        log.info("db.postgres_ts_repair.noop_no_timestamp_without_tz_columns")
    else:
        log.info("db.postgres_ts_repair.complete", altered_count=len(altered), altered=altered)


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
        app_tables = tuple(sorted(SQLModel.metadata.tables.keys()))
        async with engine.begin() as conn:
            await _repair_postgres_timestamp_columns(conn, app_tables=app_tables)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one session per request."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
