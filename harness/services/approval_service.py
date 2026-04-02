"""Human approval: validate state, persist decision JSON, update run status."""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from harness.models.run import PipelineRun
from harness.schemas.approval import ApprovalDecision, ApprovalStatus
from harness.schemas.pipeline import RunStatus
from harness.services.brand_loader import validate_brand_slug
from harness.services.state_json import json_blob_to_state

log = structlog.get_logger(__name__)


class ApprovalServiceError(Exception):
    """Business-rule violation for approval actions."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _map_run_status(decision: ApprovalStatus) -> str:
    if decision == ApprovalStatus.APPROVED:
        return RunStatus.APPROVED.value
    if decision == ApprovalStatus.REJECTED:
        return RunStatus.REJECTED.value
    return RunStatus.EDITING_LATER.value


async def list_runs_for_review(
    session: AsyncSession,
    *,
    brand_slug: str | None = None,
    status: str | None = "pending_review",
) -> list[PipelineRun]:
    """Runs for review UI; default only those awaiting a human decision."""
    if brand_slug:
        validate_brand_slug(brand_slug)
    q = select(PipelineRun).order_by(desc(PipelineRun.created_at))
    if brand_slug:
        q = q.where(PipelineRun.brand_slug == brand_slug)
    if status and status != "all":
        q = q.where(PipelineRun.status == status)
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> PipelineRun | None:
    return await session.get(PipelineRun, run_id)


async def apply_approval_decision(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    status: ApprovalStatus,
    actor: str = "",
    note: str = "",
) -> PipelineRun:
    """
    Record ApprovalDecision in approval_json and set run.status.

    Does not call WordPress or any post-approval export service.
    """
    run = await session.get(PipelineRun, run_id)
    if run is None:
        raise ApprovalServiceError("not_found", "Run does not exist.")
    if run.status != RunStatus.PENDING_REVIEW.value:
        raise ApprovalServiceError(
            "not_pending_review",
            f"Run is not awaiting review (current status: {run.status}).",
        )

    decision = ApprovalDecision(status=status, actor=actor.strip(), note=note.strip())
    run.approval_json = json.dumps(decision.model_dump(mode="json"), ensure_ascii=False)
    run.status = _map_run_status(status)
    run.touch()
    session.add(run)
    await session.commit()
    await session.refresh(run)
    log.info(
        "approval.recorded",
        run_id=str(run_id),
        decision=status.value,
        actor=actor.strip() or "(anonymous)",
    )
    return run


def review_package_from_run(run: PipelineRun) -> dict[str, Any]:
    """Normalised dict for templates / inspection from state_json."""
    state = json_blob_to_state(run.state_json)
    mx = state.get("mixed_input")
    mixed_input_json = (
        json.dumps(mx, indent=2, ensure_ascii=False)[:50_000] if mx else None
    )
    mm = (state.get("source_material") or {}).get("mixed_merge_report")
    mixed_merge_report_json = (
        json.dumps(mm, indent=2, ensure_ascii=False)[:30_000] if mm else None
    )
    wd = state.get("website_discovery_input")
    website_discovery_input_json = (
        json.dumps(wd, indent=2, ensure_ascii=False)[:30_000] if wd else None
    )
    wap = state.get("website_analysis_package")
    website_analysis_package_json = (
        json.dumps(wap, indent=2, ensure_ascii=False)[:80_000] if wap else None
    )
    pbt = state.get("proposed_brand_template")
    proposed_brand_template_json = (
        json.dumps(pbt, indent=2, ensure_ascii=False)[:40_000] if pbt else None
    )
    btr = state.get("brand_template_resolution")
    brand_template_resolution_json = (
        json.dumps(btr, indent=2, ensure_ascii=False)[:12_000] if btr else None
    )
    abt = state.get("active_brand_template")
    active_brand_template_json = (
        json.dumps(abt, indent=2, ensure_ascii=False)[:40_000] if abt else None
    )
    return {
        "run_mode": state.get("run_mode"),
        "run_intent": state.get("run_intent"),
        "brand_knowledge_snapshot": state.get("brand_knowledge_snapshot"),
        "source_material": state.get("source_material"),
        "document_input": state.get("document_input"),
        "transcript_input": state.get("transcript_input"),
        "mixed_input": state.get("mixed_input"),
        "mixed_input_json": mixed_input_json,
        "mixed_merge_report_json": mixed_merge_report_json,
        "website_discovery_input": state.get("website_discovery_input"),
        "website_discovery_input_json": website_discovery_input_json,
        "website_analysis_package": state.get("website_analysis_package"),
        "website_analysis_package_json": website_analysis_package_json,
        "proposed_brand_template": state.get("proposed_brand_template"),
        "proposed_brand_template_json": proposed_brand_template_json,
        "brand_template_resolution": state.get("brand_template_resolution"),
        "brand_template_resolution_json": brand_template_resolution_json,
        "active_brand_template": state.get("active_brand_template"),
        "active_brand_template_json": active_brand_template_json,
        "normalized_input": state.get("normalized_input"),
        "selected_topic": state.get("selected_topic"),
        "topic_candidates": state.get("topic_candidates") or [],
        "source_items": state.get("source_items") or [],
        "editorial_brief": state.get("editorial_brief"),
        "article_draft": state.get("article_draft"),
        "linkedin_post": state.get("linkedin_post"),
        "image_prompts": state.get("image_prompts"),
        "metadata_package": state.get("metadata_package"),
        "channel_output_bundle": state.get("channel_output_bundle"),
        "review_warnings": state.get("review_warnings"),
        "stage": state.get("stage"),
        "errors": state.get("errors") or [],
    }


def parse_approval(run: PipelineRun) -> ApprovalDecision | None:
    if not run.approval_json:
        return None
    try:
        data = json.loads(run.approval_json)
        return ApprovalDecision.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        return None
