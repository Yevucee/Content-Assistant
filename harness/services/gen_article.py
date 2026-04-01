"""LLM markdown article from brief + sources."""

from __future__ import annotations

import os
import re
from typing import Any

import structlog

from harness.schemas.content import ArticleDraft
from harness.schemas.sources import SourceItem
from harness.services import llm as llm_svc
from harness.services.prompts_env import get_prompt_env
from harness.services.state_helpers import numbered_sources

log = structlog.get_logger(__name__)


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").lower() in ("1", "true", "yes")


def _ensure_sources_section(body: str, items: list[SourceItem]) -> str:
    if "## sources consulted" in body.lower():
        return body
    lines = ["\n\n## Sources consulted\n"]
    for i, it in enumerate(items[:20], start=1):
        u = str(it.url)
        lines.append(f"{i}. [{it.title}]({u})\n")
    log.info("gen.article.appended_sources_section")
    return body + "".join(lines)


def _fallback_article(brief: dict[str, Any], items: list[SourceItem]) -> ArticleDraft:
    title = str(brief.get("title") or "Article")
    parts = [
        f"# {title}\n",
        "\n*(Draft generated in fallback mode — expand with full LLM or editing.)*\n",
        f"\n{brief.get('narrative_angle', '')}\n",
    ]
    for claim in (brief.get("key_claims") or [])[:5]:
        parts.append(f"\n- {claim}\n")
    body = "".join(parts)
    body = _ensure_sources_section(body, items)
    wc = len(body.split())
    return ArticleDraft(title=title, body_md=body, word_count=wc)


def generate_article(
    brand: dict[str, Any],
    brief: dict[str, Any],
    all_sources: list[SourceItem],
) -> ArticleDraft:
    if _skip_llm():
        log.info("gen.article.skip_llm")
        return _fallback_article(brief, all_sources)

    env = get_prompt_env()
    tmpl = env.get_template("article_draft.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        tone=str(brand.get("tone", "")),
        audience=str(brand.get("audience", "")),
        banned_phrases=list(brand.get("banned_phrases") or []),
        cta_style=str(brand.get("cta_style", "")),
        brief_title=str(brief.get("title", "Article")),
        brief_audience=str(brief.get("audience", "")),
        brief_angle=str(brief.get("narrative_angle", "")),
        key_claims=list(brief.get("key_claims") or []),
        suggested_structure=list(brief.get("suggested_structure") or []),
        risks=list(brief.get("risks_weak_points") or []),
        cta_direction=str(brief.get("cta_direction", "")),
        numbered_sources=numbered_sources(all_sources, limit=40),
    )
    system = (
        "You write polished markdown articles. Output markdown only — no preamble, no JSON, "
        "no code fences around the full document."
    )
    try:
        body = llm_svc.chat_text(system=system, user=user, temperature=0.42)
        if not body.strip():
            raise ValueError("empty article body")
        title = str(brief.get("title", "Article"))
        if not body.lstrip().startswith("#"):
            body = f"# {title}\n\n" + body
        body = _ensure_sources_section(body, all_sources)
        wc = len(body.split())
        log.info("gen.article.llm_ok", word_count=wc)
        return ArticleDraft(title=title, body_md=body, word_count=wc)
    except Exception as e:  # noqa: BLE001
        log.warning("gen.article.llm_failed", error=str(e))
        return _fallback_article(brief, all_sources)


def slugify_fallback(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:60] or "draft")[:60]
