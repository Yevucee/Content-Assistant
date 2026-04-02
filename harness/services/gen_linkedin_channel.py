"""LinkedIn primary + punchy + teaser in one structured pass."""

from __future__ import annotations

import os
from typing import Any

import structlog

from harness.schemas.channel_outputs import LinkedInChannelOutput
from harness.services import llm as llm_svc
from harness.services.prompts_env import get_prompt_env

log = structlog.get_logger(__name__)


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").lower() in ("1", "true", "yes")


def _coerce_hashtags(policy: str, raw: Any) -> list[str]:
    tags: list[str] = []
    if isinstance(raw, list):
        tags = [str(x).lstrip("#") for x in raw if str(x).strip()][:8]
    pol = (policy or "minimal").lower()
    if pol == "none":
        return []
    if pol == "minimal":
        return tags[:2]
    return tags[:4]


def _fallback(brand: dict[str, Any], article_title: str, excerpt: str) -> LinkedInChannelOutput:
    name = str(brand.get("name", "We"))
    primary = (
        f"New perspective: {article_title}\n\n"
        f"{excerpt[:500].strip()}…\n\n"
        f"What would you add for {brand.get('audience', 'your peers')}?"
    )
    punchy = f"{article_title}\n\n{excerpt[:200].strip()}…" if excerpt.strip() else article_title
    teaser = (excerpt.split("\n")[0][:240] if excerpt.strip() else article_title[:240])
    return LinkedInChannelOutput(
        primary=primary[:2800],
        punchy=punchy[:1200],
        teaser=teaser,
        hashtags=[],
    )


def generate_linkedin_channel(
    brand: dict[str, Any],
    article: dict[str, Any],
    brief: dict[str, Any],
) -> LinkedInChannelOutput:
    title = str(article.get("title") or brief.get("title") or "Article")
    body = str(article.get("body_md") or "")
    excerpt = body.replace("#", "").strip()[:1200]
    li = brand.get("linkedin") or {}
    if not isinstance(li, dict):
        li = {}
    policy = str(li.get("hashtag_policy", "minimal"))

    if _skip_llm():
        log.info("gen.linkedin_channel.skip_llm")
        return _fallback(brand, title, excerpt)

    env = get_prompt_env()
    tmpl = env.get_template("linkedin_variants.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        audience=str(brand.get("audience", "")),
        linkedin_tone=str(li.get("tone_notes", "")),
        hashtag_policy=policy,
        brand_knowledge_context=str(brand.get("brand_knowledge_context", "")),
        article_title=title,
        excerpt=excerpt,
    )
    system = "You output only JSON for LinkedIn variants. No markdown fencing."
    try:
        data = llm_svc.chat_json(system=system, user=user, temperature=0.45)
        primary = str(data.get("primary") or "").strip()
        if not primary:
            raise ValueError("empty primary")
        max_hint = li.get("max_chars_hint")
        if isinstance(max_hint, int) and max_hint > 0:
            primary = primary[:max_hint]
        tags = _coerce_hashtags(policy, data.get("hashtags"))
        log.info("gen.linkedin_channel.llm_ok")
        return LinkedInChannelOutput(
            primary=primary,
            punchy=str(data.get("punchy") or "")[:2000],
            teaser=str(data.get("teaser") or "")[:1200],
            hashtags=tags,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("gen.linkedin_channel.llm_failed", error=str(e))
        return _fallback(brand, title, excerpt)
