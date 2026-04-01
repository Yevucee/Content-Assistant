"""Invoke compiled graphs and persist run state."""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from harness.graphs.pipeline import build_phase1_graph, build_phase2_export_graph
from harness.models.run import PipelineRun
from harness.schemas.pipeline import PipelineStage, RunStatus
from harness.services.run_artifacts import (
    persist_run_generated_content,
    persist_run_sources_and_topics,
)
from harness.services.state_json import json_blob_to_state, state_to_json_blob
from harness.state.graph_state import initial_graph_state

log = structlog.get_logger(__name__)

_phase1 = build_phase1_graph()
_phase2 = build_phase2_export_graph()


async def create_and_run_phase1(
    session: AsyncSession,
    *,
    brand_slug: str,
) -> PipelineRun:
    """
    Create a DB row, run phase-1 graph, persist merged state JSON.

    Human approval is represented in DB after Milestone 4; export is phase 2.
    """
    run = PipelineRun(
        brand_slug=brand_slug,
        status="running",
        phase="phase1_pipeline",
        stage="init",
        state_json="{}",
    )
    session.add(run)
    await session.flush()
    canonical_id = str(run.id)
    state: dict[str, Any] = dict(initial_graph_state(canonical_id, brand_slug))

    log.info("pipeline.phase1.start", run_id=canonical_id, brand_slug=brand_slug)
    try:
        final = _phase1.invoke(state)
    except Exception as e:  # noqa: BLE001
        log.exception("pipeline.phase1.failed", run_id=canonical_id)
        final = dict(state)
        err_list = list(final.get("errors") or [])
        err_list.append(str(e))
        final["errors"] = err_list
        final["status"] = RunStatus.FAILED.value
        final["stage"] = PipelineStage.FAILED.value

    if str(final.get("status")) == RunStatus.PENDING_REVIEW.value:
        await persist_run_sources_and_topics(
            session,
            run_id=run.id,
            source_items=final.get("source_items") or [],
            topic_candidates=final.get("topic_candidates") or [],
        )
        await persist_run_generated_content(
            session,
            run_id=run.id,
            editorial_brief=final.get("editorial_brief") or {},
            article_draft=final.get("article_draft") or {},
            linkedin=final.get("linkedin_post") or {},
            image_prompts=final.get("image_prompts") or {},
            metadata_package=final.get("metadata_package") or {},
            review_warnings=final.get("review_warnings") or {},
        )

    run.state_json = state_to_json_blob(final)
    run.status = str(final.get("status", run.status))
    run.stage = str(final.get("stage", run.stage))
    run.phase = str(final.get("phase", run.phase))
    run.touch()
    session.add(run)
    await session.commit()
    await session.refresh(run)
    log.info("pipeline.phase1.done", run_id=canonical_id, status=run.status)
    return run


async def run_phase2_export(
    session: AsyncSession,
    *,
    run_db_id: uuid.UUID,
) -> PipelineRun:
    """Load state from DB, run export node graph, persist WordPress result."""
    result = await session.execute(select(PipelineRun).where(PipelineRun.id == run_db_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise ValueError(f"Run unknown: {run_db_id}")
    state = json_blob_to_state(run.state_json)
    log.info("pipeline.phase2.start", run_id=str(run_db_id))
    final = _phase2.invoke(state)
    run.state_json = state_to_json_blob(final)
    run.status = str(final.get("status", run.status))
    run.stage = str(final.get("stage", run.stage))
    run.phase = str(final.get("phase", run.phase))
    wp = final.get("wordpress_export")
    if wp:
        run.wordpress_result_json = json.dumps(wp, default=str, ensure_ascii=False)
    run.touch()
    session.add(run)
    await session.commit()
    await session.refresh(run)
    log.info("pipeline.phase2.done", run_id=str(run_db_id), status=run.status)
    return run


async def list_runs(session: AsyncSession, brand_slug: str | None = None) -> list[PipelineRun]:
    q = select(PipelineRun).order_by(desc(PipelineRun.created_at))
    if brand_slug:
        q = q.where(PipelineRun.brand_slug == brand_slug)
    res = await session.execute(q)
    return list(res.scalars().all())
