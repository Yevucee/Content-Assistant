"""Pipeline runs — list and manual trigger (Milestone 1)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from harness.models.run import PipelineRun
from harness.services.db import get_db
from harness.services import pipeline_runner
from harness.services.state_json import json_blob_to_state
from harness.services.wp_export import (
    WordPressExportServiceError,
    export_approved_run_to_wordpress,
)

router = APIRouter()


class TriggerRunBody(BaseModel):
    brand_slug: str = Field(..., description="Brand directory slug under brands/")


class WordPressDraftExportBody(BaseModel):
    """Optional body for explicit draft export (never publishes)."""

    force_new_draft: bool = Field(
        default=False,
        description="If true, create another draft even when one already succeeded.",
    )


class RunSummary(BaseModel):
    id: uuid.UUID
    brand_slug: str
    status: str
    phase: str
    stage: str
    created_at: Any
    updated_at: Any

    model_config = ConfigDict(from_attributes=True)


@router.get("")
async def list_runs(
    brand_slug: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> list[RunSummary]:
    rows = await pipeline_runner.list_runs(session, brand_slug=brand_slug)
    return [RunSummary.model_validate(r) for r in rows]


@router.post("/trigger", response_model=RunSummary)
async def trigger_run(
    body: TriggerRunBody,
    session: AsyncSession = Depends(get_db),
) -> RunSummary:
    try:
        run = await pipeline_runner.create_and_run_phase1(session, brand_slug=body.brand_slug)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return RunSummary.model_validate(run)


@router.post("/{run_id}/wordpress/draft")
async def export_wordpress_draft(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    body: WordPressDraftExportBody = Body(default_factory=WordPressDraftExportBody),
) -> dict[str, Any]:
    """Create a WordPress draft from an approved run (explicit action; draft status only)."""
    force = body.force_new_draft
    try:
        attempt = await export_approved_run_to_wordpress(
            session,
            run_id,
            force_new_draft=force,
        )
    except WordPressExportServiceError as e:
        status_map = {
            "not_found": 404,
            "not_approved": 403,
            "already_exported": 409,
        }
        code = status_map.get(e.code, 400)
        raise HTTPException(status_code=code, detail=e.message) from e
    return attempt.model_dump(mode="json")


@router.get("/{run_id}")
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from sqlmodel import select

    res = await session.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = res.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    wp = None
    if run.wordpress_result_json:
        wp = json.loads(run.wordpress_result_json)
    approval = None
    if run.approval_json:
        approval = json.loads(run.approval_json)
    return {
        "id": str(run.id),
        "brand_slug": run.brand_slug,
        "status": run.status,
        "phase": run.phase,
        "stage": run.stage,
        "state": json_blob_to_state(run.state_json),
        "approval": approval,
        "wordpress_result": wp,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }
