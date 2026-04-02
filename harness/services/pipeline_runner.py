"""Invoke compiled graphs and persist run state."""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from urllib.parse import urlparse

from harness.graphs.pipeline import build_phase1_graph
from harness.models.run import PipelineRun
from harness.schemas.inputs import (
    ExistingBlogStyleInput,
    MixedInputBundle,
    WebsiteDiscoveryInput,
)
from harness.utils.url_normalize import normalize_url
from harness.schemas.pipeline import PipelineStage, RunStatus
from harness.schemas.run_modes import RunMode
from harness.services.brand_loader import validate_brand_slug
from harness.services.document_ingestion import (
    DocumentExtractError,
    combine_pasted_and_extracted,
    extract_text_from_bytes,
)
from harness.services.run_artifacts import (
    persist_run_generated_content,
    persist_run_sources_and_topics,
)
from harness.services.state_json import state_to_json_blob
from harness.services.upload_storage import save_upload_bytes
from harness.state.graph_state import initial_graph_state

log = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _compiled_phase1_graph():
    """Lazy compile so import-time failures surface only when the pipeline runs."""
    return build_phase1_graph()


def _merge_upload_into_mixed(
    mixed: dict[str, Any],
    *,
    upload_target: str,
    combined: str,
    original_filename: str,
) -> dict[str, Any]:
    """Set document or transcript lane text to combined paste+extract result."""
    out = dict(mixed)
    tgt = (upload_target or "document").strip().casefold()
    if tgt not in ("document", "transcript"):
        tgt = "document"
    if tgt == "transcript":
        tr = dict(out.get("transcript") or {})
        tr["pasted_text"] = combined
        out["transcript"] = tr
    else:
        doc = dict(out.get("documents") or {})
        doc["pasted_text"] = combined
        if original_filename and not doc.get("source_label"):
            doc["source_label"] = original_filename
        out["documents"] = doc
    return out


def _website_discovery_from_existing_blog(raw: dict[str, Any]) -> dict[str, Any]:
    eb = ExistingBlogStyleInput.model_validate(raw)
    blog_urls = [str(u).strip() for u in (eb.blog_urls or []) if str(u).strip()]
    site_url = (eb.site_url or "").strip()
    if not site_url and blog_urls:
        first = normalize_url(blog_urls[0])
        if first:
            p = urlparse(first)
            site_url = f"{p.scheme}://{p.netloc}/"
    return {
        "website_url": site_url or None,
        "blog_urls": blog_urls,
        "brand_name": None,
        "extra_notes": None,
        "max_internal_links": 3 if eb.study_site else 0,
    }


async def create_and_run_phase1(
    session: AsyncSession,
    *,
    brand_slug: str,
    run_mode: str | None = None,
    run_intent: str | None = None,
    idea_input: dict[str, Any] | None = None,
    document_input: dict[str, Any] | None = None,
    transcript_input: dict[str, Any] | None = None,
    mixed_input: dict[str, Any] | None = None,
    website_discovery_input: dict[str, Any] | None = None,
    existing_blog_style_input: dict[str, Any] | None = None,
    source_material: dict[str, Any] | None = None,
    upload: tuple[bytes, str] | None = None,
    upload_target: str | None = None,
) -> PipelineRun:
    """
    Create a DB row, run the phase-1 LangGraph, persist merged state JSON.

    Human approval updates `PipelineRun` via the review / approval service. WordPress
    draft export is triggered separately (`wp_export.export_approved_run_to_wordpress`),
    not from this graph.
    """
    validate_brand_slug(brand_slug)
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

    sm: dict[str, Any] = dict(source_material or {})
    doc_in = dict(document_input) if document_input else None
    tr_in = dict(transcript_input) if transcript_input else None

    mode = run_mode or RunMode.SOURCE_DRIVEN.value
    mixed_in: dict[str, Any] | None = dict(mixed_input) if mixed_input is not None else None
    if mode == RunMode.MIXED.value and mixed_in is None:
        mixed_in = {}

    if upload is not None:
        raw, fname = upload
        rel = save_upload_bytes(run.id, fname, raw)
        sm["storage_relpath"] = rel
        sm["original_filename"] = fname
        try:
            extracted = extract_text_from_bytes(fname, raw)
        except DocumentExtractError as e:
            await session.delete(run)
            await session.commit()
            raise ValueError(str(e)) from e
        if mode == RunMode.MIXED.value:
            tgt = (upload_target or "document").strip().casefold()
            slot = "transcript" if tgt == "transcript" else "documents"
            nested = (mixed_in or {}).get(slot) or {}
            prev_paste = (nested.get("pasted_text") or "").strip() or None
            combined = combine_pasted_and_extracted(prev_paste, extracted)
            mixed_in = _merge_upload_into_mixed(
                mixed_in or {},
                upload_target=(upload_target or "document"),
                combined=combined,
                original_filename=fname,
            )
        else:
            pasted = ""
            if doc_in is not None:
                pasted = (doc_in.get("pasted_text") or "").strip()
            elif tr_in is not None:
                pasted = (tr_in.get("pasted_text") or "").strip()
            combined = combine_pasted_and_extracted(pasted if pasted else None, extracted)
            if doc_in is not None:
                doc_in = {**doc_in, "pasted_text": combined}
            if tr_in is not None:
                tr_in = {**tr_in, "pasted_text": combined}
        sm["extracted_chars"] = len(extracted)
        sm["combined_chars"] = len(combined)
    if mode == RunMode.DOCUMENT_DRIVEN.value and doc_in is not None:
        sm.setdefault("label", doc_in.get("source_label") or sm.get("original_filename") or "Document")
    if mode == RunMode.TRANSCRIPT_DRIVEN.value and tr_in is not None:
        sm.setdefault("label", sm.get("original_filename") or tr_in.get("title_hint") or "Transcript")

    if mode == RunMode.DOCUMENT_DRIVEN.value:
        if not doc_in:
            await session.delete(run)
            await session.commit()
            raise ValueError("document_input is required for document_driven runs.")
        if not (doc_in.get("pasted_text") or "").strip():
            await session.delete(run)
            await session.commit()
            raise ValueError("Document run has no text to process.")
    if mode == RunMode.TRANSCRIPT_DRIVEN.value:
        if not tr_in:
            await session.delete(run)
            await session.commit()
            raise ValueError("transcript_input is required for transcript_driven runs.")
        if not (tr_in.get("pasted_text") or "").strip():
            await session.delete(run)
            await session.commit()
            raise ValueError("Transcript run has no text to process.")

    if mode == RunMode.MIXED.value:
        try:
            MixedInputBundle.model_validate(mixed_in or {})
        except ValidationError as e:
            await session.delete(run)
            await session.commit()
            raise ValueError(str(e)) from e
        sm.setdefault("label", sm.get("original_filename") or "Mixed input")

    wd_in: dict[str, Any] | None = dict(website_discovery_input) if website_discovery_input else None
    if mode == RunMode.EXISTING_BLOG_STYLE.value:
        if not existing_blog_style_input:
            await session.delete(run)
            await session.commit()
            raise ValueError("existing_blog_style_input is required for existing_blog_style runs.")
        wd_in = _website_discovery_from_existing_blog(dict(existing_blog_style_input))
    if mode in (RunMode.WEBSITE_DISCOVERY.value, RunMode.EXISTING_BLOG_STYLE.value):
        if not wd_in or not str(wd_in.get("website_url") or "").strip():
            await session.delete(run)
            await session.commit()
            raise ValueError(
                "website_discovery requires website_url (or existing_blog.blog_urls to derive a site origin).",
            )
        try:
            WebsiteDiscoveryInput.model_validate(wd_in)
        except ValidationError as e:
            await session.delete(run)
            await session.commit()
            raise ValueError(str(e)) from e
        sm.setdefault("label", "Website / blog analysis")

    state: dict[str, Any] = dict(
        initial_graph_state(
            canonical_id,
            brand_slug,
            run_mode=run_mode,
            run_intent=run_intent,
            idea_input=idea_input,
            document_input=doc_in,
            transcript_input=tr_in,
            mixed_input=mixed_in if mode == RunMode.MIXED.value else None,
            website_discovery_input=wd_in
            if mode in (RunMode.WEBSITE_DISCOVERY.value, RunMode.EXISTING_BLOG_STYLE.value)
            else None,
            source_material=sm,
        )
    )

    log.info("pipeline.phase1.start", run_id=canonical_id, brand_slug=brand_slug)
    try:
        final = _compiled_phase1_graph().invoke(state)
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
            channel_outputs=final.get("channel_output_bundle") or {},
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


async def list_runs(session: AsyncSession, brand_slug: str | None = None) -> list[PipelineRun]:
    if brand_slug:
        validate_brand_slug(brand_slug)
    q = select(PipelineRun).order_by(desc(PipelineRun.created_at))
    if brand_slug:
        q = q.where(PipelineRun.brand_slug == brand_slug)
    res = await session.execute(q)
    return list(res.scalars().all())
