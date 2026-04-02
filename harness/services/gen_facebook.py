"""Facebook post drafts from shared article package."""

from __future__ import annotations

import os
from typing import Any

import structlog

from harness.schemas.channel_outputs import FacebookPost
from harness.services import llm as llm_svc
from harness.services.prompts_env import get_prompt_env

log = structlog.get_logger(__name__)


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").lower() in ("1", "true", "yes")


def _fallback(brand: dict[str, Any], title: str, excerpt: str) -> FacebookPost:
    primary = f"{title}\n\n{excerpt[:500]}…\n\n— {brand.get('name', 'Team')}"
    return FacebookPost(primary=primary[:2000], community=primary[:1600])


def generate_facebook_post(
    brand: dict[str, Any],
    article: dict[str, Any],
    brief: dict[str, Any],
) -> FacebookPost:
    title = str(article.get("title") or brief.get("title") or "Article")
    body = str(article.get("body_md") or "")
    excerpt = body.replace("#", "").strip()[:1000]
    kc = brief.get("key_claims") or []
    first_claim = str(kc[0]) if isinstance(kc, list) and kc else ""

    if _skip_llm():
        log.info("gen.facebook.skip_llm")
        return _fallback(brand, title, excerpt)

    env = get_prompt_env()
    tmpl = env.get_template("facebook_post.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        audience=str(brief.get("audience") or brand.get("audience", "")),
        banned_phrases=list(brand.get("banned_phrases") or []),
        brand_knowledge_context=str(brand.get("brand_knowledge_context", "")),
        article_title=title,
        narrative_angle=str(brief.get("narrative_angle", ""))[:2000],
        first_claim=first_claim[:800],
    )
    system = "You output only JSON for Facebook posts. No markdown fencing."
    try:
        data = llm_svc.chat_json(system=system, user=user, temperature=0.45)
        primary = str(data.get("primary") or "").strip()
        if not primary:
            raise ValueError("empty primary")
        log.info("gen.facebook.llm_ok")
        return FacebookPost(
            primary=primary[:4000],
            community=str(data.get("community") or "")[:4000],
        )
    except Exception as e:  # noqa: BLE001
        log.warning("gen.facebook.llm_failed", error=str(e))
        return _fallback(brand, title, excerpt)
