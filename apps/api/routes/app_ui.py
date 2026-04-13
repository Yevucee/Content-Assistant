"""User-facing server-rendered app: create runs and view results without the JSON API."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import markdown
import nh3
import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from starlette.templating import Jinja2Templates

from harness.models.run import PipelineRun
from harness.schemas.inputs import ManualIdeaInput, MixedInputBundle, WebsiteDiscoveryInput
from harness.schemas.run_modes import RunIntent, RunMode
from harness.services import brand_loader
from harness.services import pipeline_runner
from harness.services.db import get_db
from harness.services.state_json import json_blob_to_state

log = structlog.get_logger(__name__)

router = APIRouter()
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# (value, label) for HTML selects — only modes exposed in the product UI.
RUN_MODE_CHOICES: tuple[tuple[str, str], ...] = (
    (RunMode.IDEA_DRIVEN.value, "Idea — topic, angle, or bullets"),
    (RunMode.DOCUMENT_DRIVEN.value, "Document — paste a report, brief, or long text"),
    (RunMode.TRANSCRIPT_DRIVEN.value, "Transcript — meeting notes or interview text"),
    (RunMode.MIXED.value, "Mixed — combine idea, text, links, and instructions"),
    (RunMode.WEBSITE_DISCOVERY.value, "Website — analyze a site or blog for style and opportunities"),
)

_BRAND_NOT_FOUND_USER_MSG = "Brand not found. Please choose a valid brand."

RUN_INTENT_CHOICES: tuple[tuple[str, str], ...] = (
    (RunIntent.BLOG_PLUS_SOCIAL.value, "Blog article + social posts (default)"),
    (RunIntent.BLOG_ONLY.value, "Blog article only"),
    (RunIntent.SOCIAL_ONLY.value, "Social posts only"),
    (RunIntent.FULL_CONTENT_PACKAGE.value, "Full content package"),
    (RunIntent.IDEA_GENERATION_ONLY.value, "Ideas / planning only"),
    (RunIntent.BRAND_DISCOVERY_ONLY.value, "Brand discovery only"),
)


def _ctx(request: Request, **kwargs: Any) -> dict[str, Any]:
    return {
        "request": request,
        "app_base_url": os.environ.get("APP_BASE_URL", ""),
        **kwargs,
    }


def _split_lines(s: str) -> list[str]:
    return [line.strip() for line in (s or "").splitlines() if line.strip()]


def _friendly_persist_error(exc: BaseException) -> str:
    """User-visible message for run save failures (avoid raw tracebacks)."""
    seen: set[int] = set()
    chain: list[BaseException] = []
    e: BaseException | None = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        chain.append(e)
        e = e.__cause__ or e.__context__

    for err in chain:
        name = type(err).__name__
        if "UndefinedColumn" in name:
            return (
                "The database is missing a column this version of the app needs. "
                "Redeploy the latest API; if that does not fix it, contact support."
            )
        msg = str(err).lower()
        if "does not exist" in msg and "column" in msg:
            return (
                "The database schema does not match this version of the app. "
                "Redeploy the latest API or contact support."
            )
    return (
        "We could not save your run. Your entries are preserved below — fix any issues and try again, "
        "or contact support if it keeps failing."
    )


def _app_article_title_and_body(body_md: str, title: str) -> tuple[bool, str]:
    """
    If the markdown opens with an H1 matching ``title``, drop that line so we do not
    duplicate the heading when ``article.title`` is also shown (or when it becomes the only H1).
    """
    show_title = bool((title or "").strip())
    if not body_md or not show_title:
        return show_title, body_md
    stripped = body_md.lstrip()
    if not stripped.startswith("#"):
        return show_title, body_md
    first_line, sep, rest = stripped.partition("\n")
    h1_text = first_line.lstrip("#").strip()
    if h1_text.casefold() == title.strip().casefold():
        return False, (rest.lstrip("\n") if sep else "").lstrip()
    return show_title, body_md


def _render_safe_article_html(body_md: str, *, max_chars: int = 8000) -> tuple[str, bool]:
    """Markdown → HTML, truncated then sanitized with nh3."""
    truncated = len(body_md) > max_chars
    text = body_md[:max_chars] if truncated else body_md
    raw = markdown.markdown(
        text,
        extensions=["extra", "nl2br", "sane_lists"],
        output_format="html",
    )
    return nh3.clean(raw), truncated


def _build_mixed_from_form(
    *,
    idea_working_title: str,
    idea_angle: str,
    idea_rough: str,
    idea_notes: str,
    idea_bullets: str,
    doc_text: str,
    doc_title_hint: str,
    tr_text: str,
    tr_title_hint: str,
    tr_context: str,
    user_instructions: str,
    manual_urls: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    bullets = _split_lines(idea_bullets)
    if any(
        [
            (idea_working_title or "").strip(),
            (idea_angle or "").strip(),
            (idea_rough or "").strip(),
            (idea_notes or "").strip(),
            bullets,
        ]
    ):
        out["idea"] = {
            "working_title": (idea_working_title or "").strip() or None,
            "angle": (idea_angle or "").strip() or None,
            "rough_idea": (idea_rough or "").strip() or None,
            "notes": (idea_notes or "").strip() or None,
            "bullet_points": bullets,
        }
    if (doc_text or "").strip():
        out["documents"] = {
            "pasted_text": doc_text.strip(),
            "title_hint": (doc_title_hint or "").strip() or None,
        }
    if (tr_text or "").strip():
        out["transcript"] = {
            "pasted_text": tr_text.strip(),
            "title_hint": (tr_title_hint or "").strip() or None,
            "context_notes": (tr_context or "").strip() or None,
        }
    if (user_instructions or "").strip():
        out["user_instructions"] = user_instructions.strip()
    urls = _split_lines(manual_urls)
    if urls:
        out["sources"] = {"manual_urls": urls, "rss_feeds": []}
    return out


@router.get("/app", response_class=HTMLResponse)
async def app_dashboard(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    q = select(PipelineRun).order_by(desc(PipelineRun.created_at)).limit(30)
    res = await session.execute(q)
    runs = list(res.scalars().all())
    brands = brand_loader.list_brand_slugs()
    return templates.TemplateResponse(
        request,
        "app/dashboard.html",
        _ctx(
            request,
            title="Dashboard",
            runs=runs,
            brands=brands,
        ),
    )


@router.get("/app/new", response_class=HTMLResponse)
async def app_new_run_form(request: Request) -> HTMLResponse:
    brands = brand_loader.list_brand_slugs()
    return templates.TemplateResponse(
        request,
        "app/new_run.html",
        _ctx(
            request,
            title="New run",
            brands=brands,
            run_mode_choices=RUN_MODE_CHOICES,
            run_intent_choices=RUN_INTENT_CHOICES,
            error=None,
            form=None,
        ),
    )


@router.post("/app/new", response_class=HTMLResponse, response_model=None)
async def app_new_run_submit(
    request: Request,
    session: AsyncSession = Depends(get_db),
    brand_slug: str = Form(...),
    run_mode: str = Form(...),
    run_intent: str = Form(...),
    # Idea
    idea_working_title: str = Form(""),
    idea_angle: str = Form(""),
    idea_rough: str = Form(""),
    idea_notes: str = Form(""),
    idea_bullets: str = Form(""),
    # Document
    doc_pasted_text: str = Form(""),
    doc_title_hint: str = Form(""),
    doc_source_label: str = Form(""),
    # Transcript
    tr_pasted_text: str = Form(""),
    tr_title_hint: str = Form(""),
    tr_context_notes: str = Form(""),
    # Mixed
    mix_idea_working_title: str = Form(""),
    mix_idea_angle: str = Form(""),
    mix_idea_rough: str = Form(""),
    mix_idea_notes: str = Form(""),
    mix_idea_bullets: str = Form(""),
    mix_doc_text: str = Form(""),
    mix_doc_title: str = Form(""),
    mix_tr_text: str = Form(""),
    mix_tr_title: str = Form(""),
    mix_tr_context: str = Form(""),
    mix_instructions: str = Form(""),
    mix_urls: str = Form(""),
    # Website
    web_website_url: str = Form(""),
    web_brand_name: str = Form(""),
    web_blog_urls: str = Form(""),
    web_extra_notes: str = Form(""),
    web_max_links: str = Form("3"),
) -> HTMLResponse | RedirectResponse:
    brands = brand_loader.list_brand_slugs()
    form_snapshot: dict[str, Any] = {
        "brand_slug": brand_slug,
        "run_mode": run_mode,
        "run_intent": run_intent,
        "idea_working_title": idea_working_title,
        "idea_angle": idea_angle,
        "idea_rough": idea_rough,
        "idea_notes": idea_notes,
        "idea_bullets": idea_bullets,
        "doc_pasted_text": doc_pasted_text,
        "doc_title_hint": doc_title_hint,
        "doc_source_label": doc_source_label,
        "tr_pasted_text": tr_pasted_text,
        "tr_title_hint": tr_title_hint,
        "tr_context_notes": tr_context_notes,
        "mix_idea_working_title": mix_idea_working_title,
        "mix_idea_angle": mix_idea_angle,
        "mix_idea_rough": mix_idea_rough,
        "mix_idea_notes": mix_idea_notes,
        "mix_idea_bullets": mix_idea_bullets,
        "mix_doc_text": mix_doc_text,
        "mix_doc_title": mix_doc_title,
        "mix_tr_text": mix_tr_text,
        "mix_tr_title": mix_tr_title,
        "mix_tr_context": mix_tr_context,
        "mix_instructions": mix_instructions,
        "mix_urls": mix_urls,
        "web_website_url": web_website_url,
        "web_brand_name": web_brand_name,
        "web_blog_urls": web_blog_urls,
        "web_extra_notes": web_extra_notes,
        "web_max_links": web_max_links,
    }

    def _rerender(error: str, status: int = 400) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "app/new_run.html",
            _ctx(
                request,
                title="New run",
                brands=brands,
                run_mode_choices=RUN_MODE_CHOICES,
                run_intent_choices=RUN_INTENT_CHOICES,
                error=error,
                form=form_snapshot,
            ),
            status_code=status,
        )

    try:
        rm = RunMode(run_mode)
        ri = RunIntent(run_intent)
    except ValueError:
        return _rerender("Please choose a valid run mode and intent.")

    allowed_modes = {m[0] for m in RUN_MODE_CHOICES}
    if run_mode not in allowed_modes:
        return _rerender("This run mode is not available in the web form.")

    try:
        brand_loader.load_brand_pair(brand_slug)
    except ValueError:
        return _rerender(_BRAND_NOT_FOUND_USER_MSG, status=400)
    except FileNotFoundError:
        return _rerender(_BRAND_NOT_FOUND_USER_MSG, status=404)

    idea_payload: dict[str, Any] | None = None
    document_input: dict[str, Any] | None = None
    transcript_input: dict[str, Any] | None = None
    mixed_input: dict[str, Any] | None = None
    website_input: dict[str, Any] | None = None

    try:
        if rm == RunMode.IDEA_DRIVEN:
            bullets = _split_lines(idea_bullets)
            idea_payload = {
                "working_title": (idea_working_title or "").strip() or None,
                "angle": (idea_angle or "").strip() or None,
                "rough_idea": (idea_rough or "").strip() or None,
                "notes": (idea_notes or "").strip() or None,
                "bullet_points": bullets,
            }
            ManualIdeaInput.model_validate(idea_payload)
        elif rm == RunMode.DOCUMENT_DRIVEN:
            if not (doc_pasted_text or "").strip():
                return _rerender("Please paste the document text to process.")
            document_input = {
                "pasted_text": doc_pasted_text.strip(),
                "title_hint": (doc_title_hint or "").strip() or None,
                "source_label": (doc_source_label or "").strip() or None,
            }
        elif rm == RunMode.TRANSCRIPT_DRIVEN:
            if not (tr_pasted_text or "").strip():
                return _rerender("Please paste the transcript or notes.")
            transcript_input = {
                "pasted_text": tr_pasted_text.strip(),
                "title_hint": (tr_title_hint or "").strip() or None,
                "context_notes": (tr_context_notes or "").strip() or None,
            }
        elif rm == RunMode.MIXED:
            mixed_input = _build_mixed_from_form(
                idea_working_title=mix_idea_working_title,
                idea_angle=mix_idea_angle,
                idea_rough=mix_idea_rough,
                idea_notes=mix_idea_notes,
                idea_bullets=mix_idea_bullets,
                doc_text=mix_doc_text,
                doc_title_hint=mix_doc_title,
                tr_text=mix_tr_text,
                tr_title_hint=mix_tr_title,
                tr_context=mix_tr_context,
                user_instructions=mix_instructions,
                manual_urls=mix_urls,
            )
            MixedInputBundle.model_validate(mixed_input)
        elif rm == RunMode.WEBSITE_DISCOVERY:
            if not (web_website_url or "").strip():
                return _rerender("Please enter the main website URL to analyze.")
            blog_lines = _split_lines(web_blog_urls)
            try:
                _m = int((web_max_links or "3").strip() or "3")
            except ValueError:
                _m = 3
            website_input = {
                "website_url": web_website_url.strip(),
                "brand_name": (web_brand_name or "").strip() or None,
                "blog_urls": blog_lines,
                "extra_notes": (web_extra_notes or "").strip() or None,
                "max_internal_links": max(0, min(8, _m)),
            }
            WebsiteDiscoveryInput.model_validate(website_input)
        else:
            return _rerender("Unsupported mode.")
    except ValueError as e:
        return _rerender(str(e))

    try:
        run = await pipeline_runner.create_and_run_phase1(
            session,
            brand_slug=brand_slug,
            run_mode=rm.value,
            run_intent=ri.value,
            idea_input=idea_payload,
            document_input=document_input,
            transcript_input=transcript_input,
            mixed_input=mixed_input,
            website_discovery_input=website_input,
        )
    except ValueError as e:
        return _rerender(str(e))
    except FileNotFoundError:
        return _rerender(_BRAND_NOT_FOUND_USER_MSG, status=404)
    except Exception as e:
        log.exception("app.new_run.failed", brand_slug=brand_slug, run_mode=rm.value)
        return _rerender(_friendly_persist_error(e), status=500)

    return RedirectResponse(url=f"/app/runs/{run.id}", status_code=303)


@router.get("/app/runs/{run_id}", response_class=HTMLResponse)
async def app_run_result(
    request: Request,
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    run = await session.get(PipelineRun, run_id)
    if run is None:
        return templates.TemplateResponse(
            request,
            "app/not_found.html",
            _ctx(
                request,
                title="Run not found",
                message="We could not find that run. It may have been deleted or the link is wrong.",
            ),
            status_code=404,
        )
    state = json_blob_to_state(run.state_json)
    topic = state.get("selected_topic") if isinstance(state.get("selected_topic"), dict) else None
    brief = state.get("editorial_brief") if isinstance(state.get("editorial_brief"), dict) else None
    article = state.get("article_draft") if isinstance(state.get("article_draft"), dict) else None
    linkedin = state.get("linkedin_post") if isinstance(state.get("linkedin_post"), dict) else None
    errors = state.get("errors") if isinstance(state.get("errors"), list) else []
    channel = state.get("channel_output_bundle") if isinstance(state.get("channel_output_bundle"), dict) else None
    article_show_title = False
    article_body_html = ""
    article_truncated = False
    if article:
        body = article.get("body_md") or ""
        art_title = (article.get("title") or "").strip()
        article_show_title, body_for_md = _app_article_title_and_body(body, art_title)
        if (body_for_md or "").strip():
            article_body_html, article_truncated = _render_safe_article_html(body_for_md)
    return templates.TemplateResponse(
        request,
        "app/run_result.html",
        _ctx(
            request,
            title=f"Run — {str(run_id)[:8]}…",
            run=run,
            state=state,
            topic=topic,
            brief=brief,
            article=article,
            article_show_title=article_show_title,
            article_body_html=article_body_html,
            article_truncated=article_truncated,
            linkedin=linkedin,
            channel=channel,
            errors=errors,
        ),
    )
