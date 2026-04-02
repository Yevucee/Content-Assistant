"""Instagram captions from shared article package."""

from __future__ import annotations

import os
from typing import Any

import structlog

from harness.schemas.brand_template import BrandTemplateProfile
from harness.schemas.channel_outputs import InstagramCaption
from harness.services import llm as llm_svc
from harness.services.brand_template import template_for_prompts
from harness.services.prompts_env import get_prompt_env

log = structlog.get_logger(__name__)


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").lower() in ("1", "true", "yes")


def _fallback(title: str, excerpt: str) -> InstagramCaption:
    short = f"{title}\n\n{excerpt[:200]}…"
    return InstagramCaption(primary=short[:2200], short=short[:400], hashtags=[])


def generate_instagram_caption(
    brand: dict[str, Any],
    article: dict[str, Any],
    brief: dict[str, Any],
) -> InstagramCaption:
    title = str(article.get("title") or brief.get("title") or "Article")
    body = str(article.get("body_md") or "")
    excerpt = body.replace("#", "").strip()[:800]
    tmpl_prof: BrandTemplateProfile = template_for_prompts(brand)
    ig_tone = tmpl_prof.instagram_tone or tmpl_prof.linkedin_tone or "professional, human"

    if _skip_llm():
        log.info("gen.instagram.skip_llm")
        return _fallback(title, excerpt)

    env = get_prompt_env()
    tmpl = env.get_template("instagram_caption.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        audience=str(brief.get("audience") or brand.get("audience", "")),
        instagram_tone=ig_tone,
        brand_knowledge_context=str(brand.get("brand_knowledge_context", "")),
        article_title=title,
        narrative_angle=str(brief.get("narrative_angle", "")),
    )
    system = "You output only JSON for Instagram. No markdown fencing."
    try:
        data = llm_svc.chat_json(system=system, user=user, temperature=0.5)
        primary = str(data.get("primary") or "").strip()
        if not primary:
            raise ValueError("empty primary")
        tags_raw = data.get("hashtags")
        tags: list[str] = []
        if isinstance(tags_raw, list):
            tags = [str(t).lstrip("#") for t in tags_raw if str(t).strip()][:10]
        log.info("gen.instagram.llm_ok")
        return InstagramCaption(
            primary=primary[:2200],
            short=str(data.get("short") or "")[:600],
            hashtags=tags,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("gen.instagram.llm_failed", error=str(e))
        return _fallback(title, excerpt)
