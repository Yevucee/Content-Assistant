"""SEO / CMS metadata package generation."""

from __future__ import annotations

import os
import re
from typing import Any

import structlog

from harness.schemas.content import MetadataPackage
from harness.services import llm as llm_svc
from harness.services.gen_article import slugify_fallback
from harness.services.prompts_env import get_prompt_env

log = structlog.get_logger(__name__)


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").lower() in ("1", "true", "yes")


def _fallback_metadata(brand: dict[str, Any], title: str, body: str) -> MetadataPackage:
    meta = brand.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    cats = list(meta.get("default_categories") or [])
    excerpt = re.sub(r"\s+", " ", body.replace("#", "").strip())[:400]
    slug = slugify_fallback(title)
    return MetadataPackage(
        slug=slug,
        meta_title=title[:60],
        meta_description=(excerpt[:155] + "…") if len(excerpt) > 155 else excerpt,
        excerpt=excerpt[:500],
        alt_text_suggestion=f"Visual for: {title[:120]}",
        tags=[slug.replace("-", " ")][:1] if slug else [],
        categories=cats[:5],
    )


def _coerce_list(val: Any, max_n: int) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(x).strip() for x in val if str(x).strip()][:max_n]


def generate_metadata(
    brand: dict[str, Any],
    article: dict[str, Any],
    brief: dict[str, Any],
) -> MetadataPackage:
    title = str(article.get("title") or brief.get("title") or "Article")
    body = str(article.get("body_md") or "")
    excerpt_in = re.sub(r"\s+", " ", body.replace("#", "").strip())[:800]
    if _skip_llm():
        log.info("gen.metadata.skip_llm")
        return _fallback_metadata(brand, title, body)

    meta = brand.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    env = get_prompt_env()
    tmpl = env.get_template("metadata_package.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        default_categories=list(meta.get("default_categories") or []),
        brand_knowledge_context=str(brand.get("brand_knowledge_context", "")),
        article_title=title,
        article_excerpt=excerpt_in,
    )
    system = "You output only JSON for metadata. No markdown fencing."
    try:
        data = llm_svc.chat_json(system=system, user=user, temperature=0.35)
        slug = str(data.get("slug") or slugify_fallback(title))[:80]
        pkg = MetadataPackage(
            slug=re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-") or slugify_fallback(title),
            meta_title=str(data.get("meta_title") or title)[:70],
            meta_description=str(data.get("meta_description") or "")[:200],
            excerpt=str(data.get("excerpt") or excerpt_in)[:800],
            alt_text_suggestion=str(data.get("alt_text_suggestion") or "")[:500],
            tags=_coerce_list(data.get("tags"), 12),
            categories=_coerce_list(data.get("categories"), 8)
            or list(meta.get("default_categories") or [])[:8],
        )
        log.info("gen.metadata.llm_ok")
        return pkg
    except Exception as e:  # noqa: BLE001
        log.warning("gen.metadata.llm_failed", error=str(e))
        return _fallback_metadata(brand, title, body)
