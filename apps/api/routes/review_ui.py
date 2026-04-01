"""Server-rendered review UI — list, detail, approve / reject / editing later, WordPress draft."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import Jinja2Templates

from harness.schemas.approval import ApprovalStatus
from harness.schemas.pipeline import RunStatus
from harness.services import brand_loader
from harness.services.approval_service import (
    ApprovalServiceError,
    apply_approval_decision,
    get_run,
    list_runs_for_review,
    parse_approval,
    review_package_from_run,
)
from harness.services.db import get_db
from harness.services.wp_export import (
    WordPressExportServiceError,
    export_approved_run_to_wordpress,
    parse_journal,
)

log = structlog.get_logger(__name__)

router = APIRouter()
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _ctx(request: Request, **kwargs):
    base = {
        "request": request,
        "app_base_url": os.environ.get("APP_BASE_URL", ""),
    }
    base.update(kwargs)
    return base


def _wordpress_query_banner(request: Request) -> tuple[str | None, str]:
    code = request.query_params.get("wp_export")
    if code == "blocked":
        return (
            "warn",
            "A WordPress draft was already created for this run. "
            'Use "Create another draft" if you need a second post.',
        )
    if code == "error":
        return ("err", request.query_params.get("wp_msg") or "WordPress export failed.")
    if code == "done":
        return ("ok", "Last export attempt finished — see status below.")
    return (None, "")


@router.get("", response_class=HTMLResponse)
async def review_run_list(
    request: Request,
    brand_slug: str | None = None,
    status: str = "pending_review",
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Filterable list of runs (default: awaiting review)."""
    runs = await list_runs_for_review(session, brand_slug=brand_slug, status=status)
    brands = brand_loader.list_brand_slugs()
    return templates.TemplateResponse(
        request,
        "review/run_list.html",
        _ctx(
            request,
            title="Review queue",
            runs=runs,
            brands=brands,
            current_brand=brand_slug or "",
            current_status=status,
        ),
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def review_run_detail(
    request: Request,
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    run = await get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    pkg = review_package_from_run(run)
    approval = parse_approval(run)
    can_decide = run.status == RunStatus.PENDING_REVIEW.value
    wp_journal = parse_journal(run)
    _wp_ok = wp_journal.last_succeeded()
    wp_can_primary = run.status == RunStatus.APPROVED.value and _wp_ok is None
    wp_can_force = run.status == RunStatus.APPROVED.value and _wp_ok is not None
    banner_kind, banner_text = _wordpress_query_banner(request)
    return templates.TemplateResponse(
        request,
        "review/run_detail.html",
        _ctx(
            request,
            title=f"Run {str(run_id)[:8]}…",
            run=run,
            pkg=pkg,
            approval=approval,
            can_decide=can_decide,
            wp_journal=wp_journal,
            wp_can_primary=wp_can_primary,
            wp_can_force=wp_can_force,
            wp_banner_kind=banner_kind,
            wp_banner_text=banner_text,
        ),
    )


@router.post("/runs/{run_id}/approve")
async def review_approve(
    request: Request,
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    note: str = Form(""),
    actor: str = Form(""),
) -> RedirectResponse:
    try:
        await apply_approval_decision(
            session,
            run_id,
            status=ApprovalStatus.APPROVED,
            actor=actor,
            note=note,
        )
    except ApprovalServiceError as e:
        log.warning("review.approve_denied", run_id=str(run_id), reason=e.code)
        raise HTTPException(status_code=400, detail=e.message) from e
    return RedirectResponse(url=f"/review/runs/{run_id}", status_code=303)


@router.post("/runs/{run_id}/reject")
async def review_reject(
    request: Request,
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    note: str = Form(""),
    actor: str = Form(""),
) -> RedirectResponse:
    try:
        await apply_approval_decision(
            session,
            run_id,
            status=ApprovalStatus.REJECTED,
            actor=actor,
            note=note,
        )
    except ApprovalServiceError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
    return RedirectResponse(url=f"/review/runs/{run_id}", status_code=303)


@router.post("/runs/{run_id}/editing-later")
async def review_editing_later(
    request: Request,
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    note: str = Form(""),
    actor: str = Form(""),
) -> RedirectResponse:
    try:
        await apply_approval_decision(
            session,
            run_id,
            status=ApprovalStatus.EDITING_LATER,
            actor=actor,
            note=note,
        )
    except ApprovalServiceError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
    return RedirectResponse(url=f"/review/runs/{run_id}", status_code=303)


@router.post("/runs/{run_id}/wordpress-draft")
async def review_wordpress_draft(
    request: Request,
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    force_new_draft: str = Form(""),
) -> RedirectResponse:
    """Explicit action: create a WordPress draft from an approved run only."""
    force = (force_new_draft or "").strip().lower() in ("1", "on", "true", "yes")
    try:
        await export_approved_run_to_wordpress(session, run_id, force_new_draft=force)
    except WordPressExportServiceError as e:
        log.warning(
            "review.wordpress_denied",
            run_id=str(run_id),
            reason=e.code,
        )
        if e.code == "already_exported":
            return RedirectResponse(
                url=f"/review/runs/{run_id}?wp_export=blocked",
                status_code=303,
            )
        msg = quote(e.message[:900], safe="")
        return RedirectResponse(
            url=f"/review/runs/{run_id}?wp_export=error&wp_msg={msg}",
            status_code=303,
        )
    return RedirectResponse(url=f"/review/runs/{run_id}?wp_export=done", status_code=303)
