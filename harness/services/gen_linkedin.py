"""LinkedIn companion post generation."""

from __future__ import annotations

import os
from typing import Any

import structlog

from harness.schemas.content import LinkedInPost
from harness.services import llm as llm_svc
from harness.services.prompts_env import get_prompt_env

log = structlog.get_logger(__name__)


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").lower() in ("1", "true", "yes")


def _fallback_linkedin(brand: dict[str, Any], article_title: str, excerpt: str) -> LinkedInPost:
    name = str(brand.get("name", "We"))
    text = (
        f"New on our blog: {article_title}\n\n"
        f"{excerpt[:400].strip()}…\n\n"
        f"Would love your take — especially if you care about {brand.get('audience', 'this space')}."
    )
    return LinkedInPost(text=text[:2800], hashtags=[])


def _coerce_hashtags(policy: str, raw: Any) -> list[str]:
    tags: list[str] = []
    if isinstance(raw, list):
        tags = [str(x).lstrip("#") for x in raw if str(x).strip()][:6]
    pol = (policy or "minimal").lower()
    if pol == "none":
        return []
    if pol == "minimal":
        return tags[:2]
    return tags[:4]


def generate_linkedin(
    brand: dict[str, Any],
    article: dict[str, Any],
    brief: dict[str, Any],
) -> LinkedInPost:
    title = str(article.get("title") or brief.get("title") or "Article")
    body = str(article.get("body_md") or "")
    excerpt = body.replace("#", "").strip()[:800]
    if _skip_llm():
        log.info("gen.linkedin.skip_llm")
        return _fallback_linkedin(brand, title, excerpt)

    li = brand.get("linkedin") or {}
    if not isinstance(li, dict):
        li = {}
    env = get_prompt_env()
    tmpl = env.get_template("linkedin_post.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        linkedin_tone=str(li.get("tone_notes", "")),
        hashtag_policy=str(li.get("hashtag_policy", "minimal")),
        audience=str(brand.get("audience", "")),
        banned_phrases=list(brand.get("banned_phrases") or []),
        article_title=title,
        article_excerpt=excerpt[:1200],
    )
    system = "You output only JSON for the LinkedIn post. No markdown fencing."
    try:
        data = llm_svc.chat_json(system=system, user=user, temperature=0.45)
        text = str(data.get("text") or "").strip()
        tags = _coerce_hashtags(str(li.get("hashtag_policy", "minimal")), data.get("hashtags"))
        if not text:
            raise ValueError("empty linkedin text")
        max_hint = li.get("max_chars_hint")
        if isinstance(max_hint, int) and max_hint > 0:
            text = text[: max_hint]
        log.info("gen.linkedin.llm_ok")
        return LinkedInPost(text=text, hashtags=tags)
    except Exception as e:  # noqa: BLE001
        log.warning("gen.linkedin.llm_failed", error=str(e))
        return _fallback_linkedin(brand, title, excerpt)
