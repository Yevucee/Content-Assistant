"""Pipeline runs — list and manual trigger (Milestone 1)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from harness.models.run import PipelineRun
from harness.schemas.inputs import (
    DocumentInput,
    ExistingBlogStyleInput,
    ManualIdeaInput,
    MixedInputBundle,
    TranscriptInput,
    WebsiteDiscoveryInput,
)
from harness.schemas.run_modes import DEFAULT_RUN_INTENT, DEFAULT_RUN_MODE, RunIntent, RunMode
from harness.services.brand_loader import validate_brand_slug
from harness.services.db import get_db
from harness.services import pipeline_runner
from harness.services.state_json import json_blob_to_state
from harness.services.upload_storage import MAX_UPLOAD_BYTES
from harness.services.wp_export import (
    WordPressExportServiceError,
    export_approved_run_to_wordpress,
)

router = APIRouter()
log = structlog.get_logger(__name__)


def _pipeline_trigger_http_error(
    *,
    endpoint: str,
    brand_slug: str,
    run_mode: str,
) -> HTTPException:
    """Log full traceback (call only from ``except``); return safe structured JSON (no secrets)."""
    log.exception(
        "runs.trigger_failed",
        endpoint=endpoint,
        brand_slug=brand_slug,
        run_mode=run_mode,
    )
    return HTTPException(
        status_code=500,
        detail={
            "error": "pipeline_trigger_failed",
            "message": "Run creation failed; see server logs for the traceback.",
            "stage": "create_and_run_phase1",
            "brand_slug": brand_slug,
            "run_mode": run_mode,
        },
    )


async def _read_upload_bytes(file: UploadFile) -> tuple[bytes, str]:
    """Read multipart file with a hard size cap to avoid OOM."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum size ({MAX_UPLOAD_BYTES // (1024 * 1024)} MiB)",
            )
        chunks.append(chunk)
    return b"".join(chunks), (file.filename or "upload")


class TriggerRunBody(BaseModel):
    brand_slug: str = Field(..., description="Brand directory slug under brands/")
    run_mode: RunMode = Field(
        default=DEFAULT_RUN_MODE,
        description="Entry path: source, idea, document, transcript, mixed, website_discovery, existing_blog_style.",
    )
    run_intent: RunIntent = Field(
        default=DEFAULT_RUN_INTENT,
        description="What to emphasise; social_only skips full article.",
    )
    idea: ManualIdeaInput | None = Field(
        default=None,
        description="Required when run_mode is idea_driven.",
    )
    document: DocumentInput | None = Field(
        default=None,
        description="Required when run_mode is document_driven (pasted_text).",
    )
    transcript: TranscriptInput | None = Field(
        default=None,
        description="Required when run_mode is transcript_driven (pasted_text).",
    )
    mixed: MixedInputBundle | None = Field(
        default=None,
        description="Required when run_mode is mixed; combines idea, documents, transcript, URLs, instructions.",
    )
    website: WebsiteDiscoveryInput | None = Field(
        default=None,
        description="Required when run_mode is website_discovery (primary site URL + optional blog_urls).",
    )
    existing_blog: ExistingBlogStyleInput | None = Field(
        default=None,
        description="Required when run_mode is existing_blog_style; blog URLs and optional site_url.",
    )


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
    if brand_slug is not None:
        try:
            validate_brand_slug(brand_slug)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    rows = await pipeline_runner.list_runs(session, brand_slug=brand_slug)
    return [RunSummary.model_validate(r) for r in rows]


@router.post("/trigger", response_model=RunSummary)
async def trigger_run(
    body: TriggerRunBody,
    session: AsyncSession = Depends(get_db),
) -> RunSummary:
    if body.run_mode == RunMode.IDEA_DRIVEN and body.idea is None:
        raise HTTPException(
            status_code=400,
            detail="idea payload is required when run_mode is idea_driven",
        )
    if body.run_mode == RunMode.DOCUMENT_DRIVEN:
        if body.document is None:
            raise HTTPException(
                status_code=400,
                detail="document payload is required when run_mode is document_driven",
            )
        if not (body.document.pasted_text or "").strip():
            raise HTTPException(
                status_code=400,
                detail="document.pasted_text is required for JSON trigger; use POST /runs/trigger/upload for files",
            )
    if body.run_mode == RunMode.TRANSCRIPT_DRIVEN:
        if body.transcript is None:
            raise HTTPException(
                status_code=400,
                detail="transcript payload is required when run_mode is transcript_driven",
            )
        if not (body.transcript.pasted_text or "").strip():
            raise HTTPException(
                status_code=400,
                detail="transcript.pasted_text is required for JSON trigger; use POST /runs/trigger/upload for files",
            )
    if body.run_mode == RunMode.MIXED:
        if body.mixed is None:
            raise HTTPException(
                status_code=400,
                detail="mixed payload is required when run_mode is mixed",
            )
    if body.run_mode == RunMode.WEBSITE_DISCOVERY:
        if body.website is None:
            raise HTTPException(
                status_code=400,
                detail="website payload is required when run_mode is website_discovery",
            )
        if not (body.website.website_url or "").strip():
            raise HTTPException(
                status_code=400,
                detail="website.website_url is required for website_discovery",
            )
    if body.run_mode == RunMode.EXISTING_BLOG_STYLE:
        if body.existing_blog is None:
            raise HTTPException(
                status_code=400,
                detail="existing_blog payload is required when run_mode is existing_blog_style",
            )
        eb = body.existing_blog
        if not (eb.site_url or "").strip() and not eb.blog_urls:
            raise HTTPException(
                status_code=400,
                detail="existing_blog requires site_url and/or blog_urls",
            )

    idea_payload = body.idea.model_dump(mode="json", exclude_none=True) if body.idea else None
    doc_payload = body.document.model_dump(mode="json", exclude_none=True) if body.document else None
    tr_payload = body.transcript.model_dump(mode="json", exclude_none=True) if body.transcript else None
    mixed_payload = body.mixed.model_dump(mode="json", exclude_none=True) if body.mixed else None
    website_payload = body.website.model_dump(mode="json", exclude_none=True) if body.website else None
    existing_blog_payload = (
        body.existing_blog.model_dump(mode="json", exclude_none=True) if body.existing_blog else None
    )
    try:
        run = await pipeline_runner.create_and_run_phase1(
            session,
            brand_slug=body.brand_slug,
            run_mode=body.run_mode.value,
            run_intent=body.run_intent.value,
            idea_input=idea_payload,
            document_input=doc_payload,
            transcript_input=tr_payload,
            mixed_input=mixed_payload,
            website_discovery_input=website_payload,
            existing_blog_style_input=existing_blog_payload,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise _pipeline_trigger_http_error(
            endpoint="POST /runs/trigger",
            brand_slug=body.brand_slug,
            run_mode=body.run_mode.value,
        ) from e
    return RunSummary.model_validate(run)


@router.post("/trigger/upload", response_model=RunSummary)
async def trigger_run_upload(
    session: AsyncSession = Depends(get_db),
    brand_slug: str = Form(...),
    run_mode: str = Form(...),
    run_intent: str = Form(DEFAULT_RUN_INTENT.value),
    file: UploadFile | None = File(None),
    pasted_text: str = Form(""),
    title_hint: str = Form(""),
    source_label: str = Form(""),
    context_notes: str = Form(""),
    mixed_bundle_json: str = Form("{}"),
    upload_target: str = Form("document"),
) -> RunSummary:
    """
    Multipart trigger for document_driven, transcript_driven, or mixed runs.
    Provide a file (.txt, .md, .pdf, .docx) and/or pasted_text (document/transcript modes).
    For mixed, pass mixed_bundle_json and optional file (merge into document or transcript per upload_target).
    """
    try:
        rm = RunMode(run_mode)
        ri = RunIntent(run_intent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid run_mode or run_intent: {e}") from e
    if rm not in (RunMode.DOCUMENT_DRIVEN, RunMode.TRANSCRIPT_DRIVEN, RunMode.MIXED):
        raise HTTPException(
            status_code=400,
            detail="run_mode must be document_driven, transcript_driven, or mixed for upload trigger",
        )

    raw: bytes | None = None
    fname: str | None = None
    if file is not None and file.filename:
        raw, fname = await _read_upload_bytes(file)

    if rm == RunMode.MIXED:
        try:
            mix_dict = json.loads(mixed_bundle_json or "{}")
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"mixed_bundle_json must be valid JSON: {e}") from e
        if not isinstance(mix_dict, dict):
            raise HTTPException(status_code=400, detail="mixed_bundle_json must be a JSON object")
        if not raw and not mix_dict:
            raise HTTPException(status_code=400, detail="mixed_bundle_json cannot be empty when no file is uploaded")
        upload_tuple: tuple[bytes, str] | None = None
        if raw is not None and fname:
            upload_tuple = (raw, fname)
        try:
            run = await pipeline_runner.create_and_run_phase1(
                session,
                brand_slug=brand_slug,
                run_mode=rm.value,
                run_intent=ri.value,
                mixed_input=mix_dict,
                upload=upload_tuple,
                upload_target=upload_target or "document",
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise _pipeline_trigger_http_error(
                endpoint="POST /runs/trigger/upload",
                brand_slug=brand_slug,
                run_mode=rm.value,
            ) from e
        return RunSummary.model_validate(run)

    if not raw and not (pasted_text or "").strip():
        raise HTTPException(status_code=400, detail="Provide a file and/or pasted_text")
    upload_tuple = (raw, fname) if raw is not None and fname else None

    doc_input: dict | None = None
    tr_input: dict | None = None
    if rm == RunMode.DOCUMENT_DRIVEN:
        doc_input = {
            "pasted_text": pasted_text or "",
            "title_hint": title_hint or None,
            "source_label": source_label or fname or None,
        }
    else:
        tr_input = {
            "pasted_text": pasted_text or "",
            "title_hint": title_hint or None,
            "context_notes": context_notes or None,
        }

    try:
        run = await pipeline_runner.create_and_run_phase1(
            session,
            brand_slug=brand_slug,
            run_mode=rm.value,
            run_intent=ri.value,
            document_input=doc_input,
            transcript_input=tr_input,
            upload=upload_tuple,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise _pipeline_trigger_http_error(
            endpoint="POST /runs/trigger/upload",
            brand_slug=brand_slug,
            run_mode=rm.value,
        ) from e
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
            "invalid_brand": 400,
        }
        code = status_map.get(e.code, 400)
        raise HTTPException(status_code=code, detail=e.message) from e
    return attempt.model_dump(mode="json")


@router.get("/{run_id}/proposed-brand-template")
async def get_run_proposed_brand_template(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Proposed ``BrandTemplateProfile`` from a website / analysis run (temporary until saved)."""
    from sqlmodel import select

    res = await session.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = res.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    state = json_blob_to_state(run.state_json)
    proposed = state.get("proposed_brand_template")
    if not proposed:
        raise HTTPException(
            status_code=404,
            detail="This run has no proposed_brand_template (e.g. not a website discovery run).",
        )
    return {
        "run_id": str(run_id),
        "brand_slug": run.brand_slug,
        "proposed": proposed,
    }


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
