"""Server-rendered review UI — list, detail, approve / reject / editing later, WordPress draft."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from pydantic import ValidationError
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import Jinja2Templates

from harness.schemas.approval import ApprovalStatus
from harness.schemas.brand_template import BrandTemplateProfile
from harness.schemas.pipeline import RunStatus
from harness.services import brand_loader
from harness.services import brand_template_storage
from harness.services.approval_service import (
    ApprovalServiceError,
    apply_approval_decision,
    get_run,
    list_runs_for_review,
    parse_approval,
    review_package_from_run,
)
from harness.services.db import get_db
from harness.services.state_json import json_blob_to_state
from harness.services.wp_export import (
    WordPressExportServiceError,
    export_approved_run_to_wordpress,
    parse_journal,
)

log = structlog.get_logger(__name__)

router = APIRouter()
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _load_brand_pair_http(slug: str):
    try:
        return brand_loader.load_brand_pair(slug)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def _ctx(request: Request, **kwargs):
    base = {
        "request": request,
        "app_base_url": os.environ.get("APP_BASE_URL", ""),
    }
    base.update(kwargs)
    return base


def _review_not_found(request: Request, *, title: str, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "review/not_found.html",
        _ctx(request, title=title, message=message),
        status_code=404,
    )


def _display_cell(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, (dict, list)):
        return json.dumps(v, indent=2, ensure_ascii=False)[:6000]
    return str(v)[:6000]


def _template_compare_rows(
    saved: dict[str, Any] | None,
    proposed: dict[str, Any],
) -> list[dict[str, Any]]:
    keys = sorted(BrandTemplateProfile.model_fields.keys())
    s = saved or {}
    rows: list[dict[str, Any]] = []
    for k in keys:
        sv = s.get(k) if saved is not None else None
        pv = proposed.get(k) if isinstance(proposed, dict) else None
        same = (saved is not None) and (sv == pv)
        if saved is None:
            sd = "(no active file)"
        else:
            sd = _display_cell(sv)
        rows.append(
            {
                "field": k,
                "same": same,
                "saved_display": sd,
                "proposed_display": _display_cell(pv),
            },
        )
    return rows


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
    brand_slug: str | None = Query(None),
    status: str = Query("pending_review"),
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Filterable list of runs (default: awaiting review)."""
    bs = (brand_slug or "").strip() or None
    runs = await list_runs_for_review(session, brand_slug=bs, status=status)
    brands = brand_loader.list_brand_slugs()
    return templates.TemplateResponse(
        request,
        "review/run_list.html",
        _ctx(
            request,
            title="Review queue",
            runs=runs,
            brands=brands,
            current_brand=bs or "",
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
        return _review_not_found(
            request,
            title="Run not found",
            message='No run exists with this id. Check the link or open the <a href="/review">review queue</a>.',
        )
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


@router.get("/brands/{slug}/brand-template", response_class=HTMLResponse)
async def review_brand_template_editor(
    request: Request,
    slug: str,
    seed_run_id: uuid.UUID | None = Query(None, description="Seed editor from this run's proposed template"),
    saved: str | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    brand, _sources = _load_brand_pair_http(slug)
    base_prof = BrandTemplateProfile.from_brand_config_dict(brand.model_dump(mode="json"))
    active_prof, active_err = brand_template_storage.load_active_brand_template_optional(slug)
    path = brand_template_storage.active_brand_template_path(slug)
    initial: dict[str, Any]
    seed_label: str
    if seed_run_id is not None:
        run = await get_run(session, seed_run_id)
        if run is None or run.brand_slug != slug:
            return _review_not_found(
                request,
                title="Run not found",
                message="That run does not exist or belongs to another brand.",
            )
        st = json_blob_to_state(run.state_json)
        p = st.get("proposed_brand_template")
        if not p or not isinstance(p, dict):
            return _review_not_found(
                request,
                title="Nothing to seed",
                message="That run has no proposed_brand_template to load into the editor.",
            )
        initial = p
        seed_label = f"proposed template from run {seed_run_id}"
    elif active_prof is not None:
        initial = active_prof.model_dump(mode="json")
        seed_label = "current contents of brand_template.yaml"
    else:
        initial = base_prof.model_dump(mode="json")
        if active_err:
            seed_label = f"baseline from brand.yaml (active file invalid: {active_err})"
        else:
            seed_label = "baseline from brand.yaml (no active template file yet)"
    profile_json = json.dumps(initial, indent=2, ensure_ascii=False)
    warn = f"Active file on disk is invalid YAML/schema: {active_err}" if active_err else None
    using_brand_yaml_baseline = seed_run_id is None and active_prof is None
    return templates.TemplateResponse(
        request,
        "review/brand_template_edit.html",
        _ctx(
            request,
            title=f"Brand template — {slug}",
            slug=slug,
            profile_json=profile_json,
            seed_label=seed_label,
            file_exists=path.is_file(),
            saved=(saved or "") == "1",
            error=warn,
            using_brand_yaml_baseline=using_brand_yaml_baseline,
        ),
    )


@router.post("/brands/{slug}/brand-template/save", response_class=HTMLResponse)
async def review_brand_template_save(
    request: Request,
    slug: str,
    profile_json: str = Form(""),
    confirm_replace: str = Form(""),
) -> HTMLResponse:
    _load_brand_pair_http(slug)
    path = brand_template_storage.active_brand_template_path(slug)
    file_exists = path.is_file()
    ok_confirm = (confirm_replace or "").strip().lower() in ("1", "on", "true", "yes")
    if not ok_confirm:
        return templates.TemplateResponse(
            request,
            "review/brand_template_edit.html",
            _ctx(
                request,
                title=f"Brand template — {slug}",
                slug=slug,
                profile_json=profile_json,
                seed_label="(unchanged — confirm the checkbox to save)",
                file_exists=file_exists,
                saved=False,
                error="Check the confirmation box to write brand_template.yaml.",
            ),
            status_code=400,
        )
    try:
        raw = json.loads(profile_json or "{}")
        prof = BrandTemplateProfile.model_validate(raw)
    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        return templates.TemplateResponse(
            request,
            "review/brand_template_edit.html",
            _ctx(
                request,
                title=f"Brand template — {slug}",
                slug=slug,
                profile_json=profile_json,
                seed_label="(fix JSON — not saved)",
                file_exists=file_exists,
                saved=False,
                error=f"Invalid profile: {e}",
            ),
            status_code=400,
        )
    brand_template_storage.save_active_brand_template(slug, prof)
    return RedirectResponse(url=f"/review/brands/{slug}/brand-template?saved=1", status_code=303)


@router.get("/brands/{slug}/brand-template/compare", response_class=HTMLResponse)
async def review_brand_template_compare(
    request: Request,
    slug: str,
    run_id: uuid.UUID = Query(..., description="Run whose proposed_brand_template to compare"),
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    _load_brand_pair_http(slug)
    run = await get_run(session, run_id)
    if run is None or run.brand_slug != slug:
        return _review_not_found(
            request,
            title="Run not found",
            message="That run does not exist or belongs to another brand.",
        )
    st = json_blob_to_state(run.state_json)
    proposed = st.get("proposed_brand_template")
    if not isinstance(proposed, dict) or not proposed:
        return _review_not_found(
            request,
            title="Nothing to compare",
            message="This run has no proposed brand template on record.",
        )
    active, _err = brand_template_storage.load_active_brand_template_optional(slug)
    saved_dump = active.model_dump(mode="json") if active is not None else None
    rows = _template_compare_rows(saved_dump, proposed)
    return templates.TemplateResponse(
        request,
        "review/brand_template_compare.html",
        _ctx(
            request,
            title=f"Compare templates — {slug}",
            slug=slug,
            run_id=str(run_id),
            proposed=proposed,
            rows=rows,
        ),
    )
