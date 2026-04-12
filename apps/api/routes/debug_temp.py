# Mounted only when ENABLE_DEBUG_ROUTES=1 (see apps.api.routes). Default off in production.

"""Temporary debug routes that return execution breadcrumbs in JSON (no log tail required)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from harness.models.run import PipelineRun
from harness.schemas.run_modes import RunMode
from harness.services import pipeline_runner
from harness.services.brand_loader import validate_brand_slug
from harness.services.db import get_db, get_database_url, get_engine, get_session_factory

router = APIRouter(prefix="/debug", tags=["debug-temporary"])


def _engine_kind() -> str:
    url = get_database_url()
    return "sqlite" if url.startswith("sqlite") else "postgres"


@router.get("/db-check")
async def debug_db_check() -> dict[str, Any]:
    """
    TEMPORARY — remove with TODO(RAILWAY_DEBUG_REMOVE).
    Verify async engine, session factory, and a trivial query (no secrets in response).
    """
    breadcrumbs: list[str] = []
    last_ok: str | None = None
    error: dict[str, str] | None = None
    try:
        breadcrumbs.append("debug.db_check.entered")
        last_ok = breadcrumbs[-1]
        get_engine()
        breadcrumbs.append("debug.db_check.engine_created")
        last_ok = breadcrumbs[-1]
        factory = get_session_factory()
        breadcrumbs.append("debug.db_check.session_factory_ok")
        last_ok = breadcrumbs[-1]
        async with factory() as session:
            breadcrumbs.append("debug.db_check.session_opened")
            last_ok = breadcrumbs[-1]
            await session.execute(text("SELECT 1"))
            breadcrumbs.append("debug.db_check.query_ok")
            last_ok = breadcrumbs[-1]
        breadcrumbs.append("debug.db_check.done")
        last_ok = breadcrumbs[-1]
    except Exception as e:  # noqa: BLE001 — intentional broad catch for diagnostics
        error = {"exception_type": type(e).__name__, "message": str(e)}
        breadcrumbs.append("debug.db_check.failed")
    return {
        "temporary": True,
        "remove_note": "TODO(RAILWAY_DEBUG_REMOVE)",
        "ok": error is None,
        "breadcrumbs": breadcrumbs,
        "last_successful_step": last_ok,
        "engine_kind": _engine_kind(),
        "error": error,
    }


class TriggerCheckBody(BaseModel):
    brand_slug: str = Field(..., min_length=1)
    invoke_graph: bool = Field(
        default=False,
        description="If true, runs full create_and_run_phase1 (expensive; persists a run).",
    )
    run_mode: str | None = Field(
        default=None,
        description="For invoke_graph only; defaults to source_driven.",
    )


@router.post("/trigger-check")
async def debug_trigger_check(
    body: TriggerCheckBody,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    TEMPORARY — remove with TODO(RAILWAY_DEBUG_REMOVE).
    Dry-run: validate brand, insert PipelineRun, flush, then rollback (no graph, no persist).
    With invoke_graph=true: runs full pipeline once (persists).
    """
    breadcrumbs: list[str] = []
    last_ok: str | None = None
    error: dict[str, str] | None = None
    trigger_step_at_end: str | None = None

    try:
        breadcrumbs.append("debug.trigger_check.entered")
        last_ok = breadcrumbs[-1]

        validate_brand_slug(body.brand_slug)
        breadcrumbs.append("debug.trigger_check.brand_validated")
        last_ok = breadcrumbs[-1]

        if body.invoke_graph:
            rm = (body.run_mode or RunMode.SOURCE_DRIVEN.value).strip()
            try:
                RunMode(rm)
            except ValueError as e:
                error = {"exception_type": "ValueError", "message": str(e)}
                breadcrumbs.append("debug.trigger_check.invalid_run_mode")
                return _trigger_check_response(breadcrumbs, last_ok, error, None)

            breadcrumbs.append("debug.trigger_check.before_create_and_run_phase1")
            last_ok = breadcrumbs[-1]
            await pipeline_runner.create_and_run_phase1(
                session,
                brand_slug=body.brand_slug,
                run_mode=rm,
            )
            trigger_step_at_end = pipeline_runner.get_trigger_trace_step()
            breadcrumbs.append("debug.trigger_check.after_create_and_run_phase1")
            last_ok = breadcrumbs[-1]
            breadcrumbs.append("debug.trigger_check.done")
            last_ok = breadcrumbs[-1]
            return _trigger_check_response(breadcrumbs, last_ok, None, trigger_step_at_end)

        run = PipelineRun(
            brand_slug=body.brand_slug,
            status="running",
            phase="phase1_pipeline",
            stage="init",
            state_json="{}",
        )
        breadcrumbs.append("debug.trigger_check.pipeline_run_object_created")
        last_ok = breadcrumbs[-1]
        session.add(run)
        breadcrumbs.append("debug.trigger_check.before_session_flush")
        last_ok = breadcrumbs[-1]
        await session.flush()
        breadcrumbs.append("debug.trigger_check.after_session_flush")
        last_ok = breadcrumbs[-1]
        await session.rollback()
        breadcrumbs.append("debug.trigger_check.rolled_back_no_persist")
        last_ok = breadcrumbs[-1]
        breadcrumbs.append("debug.trigger_check.done")
        last_ok = breadcrumbs[-1]
    except Exception as e:  # noqa: BLE001
        error = {"exception_type": type(e).__name__, "message": str(e)}
        breadcrumbs.append("debug.trigger_check.failed")
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        trigger_step_at_end = pipeline_runner.get_trigger_trace_step()

    return _trigger_check_response(breadcrumbs, last_ok, error, trigger_step_at_end)


def _trigger_check_response(
    breadcrumbs: list[str],
    last_successful_step: str | None,
    error: dict[str, str] | None,
    pipeline_trigger_step: str | None,
) -> dict[str, Any]:
    return {
        "temporary": True,
        "remove_note": "TODO(RAILWAY_DEBUG_REMOVE)",
        "ok": error is None,
        "breadcrumbs": breadcrumbs,
        "last_successful_step": last_successful_step,
        "pipeline_trigger_step": pipeline_trigger_step,
        "engine_kind": _engine_kind(),
        "error": error,
    }
