"""Pack of social post angles from one editorial core."""

from __future__ import annotations

import os
from typing import Any

import structlog

from harness.schemas.channel_outputs import SocialIdeaPack, SocialPostAngle
from harness.services import llm as llm_svc
from harness.services.prompts_env import get_prompt_env

log = structlog.get_logger(__name__)


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").lower() in ("1", "true", "yes")


def _fallback(title: str, angle: str) -> SocialIdeaPack:
    return SocialIdeaPack(
        angles=[
            SocialPostAngle(title="Contrarian take", hook=title, platform_notes="LinkedIn thread"),
            SocialPostAngle(title="Story hook", hook=angle[:200], platform_notes="Instagram / visual"),
            SocialPostAngle(title="Tactical list", hook=f"Three lessons from: {title}", platform_notes="Facebook / casual"),
        ]
    )


def generate_social_idea_pack(
    brand: dict[str, Any],
    article: dict[str, Any],
    brief: dict[str, Any],
) -> SocialIdeaPack:
    title = str(article.get("title") or brief.get("title") or "Topic")
    angle = str(brief.get("narrative_angle", ""))

    if _skip_llm():
        log.info("gen.social_ideas.skip_llm")
        return _fallback(title, angle)

    env = get_prompt_env()
    tmpl = env.get_template("social_ideas_pack.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        audience=str(brief.get("audience") or brand.get("audience", "")),
        brand_knowledge_context=str(brand.get("brand_knowledge_context", "")),
        article_title=title,
        narrative_angle=angle,
    )
    system = "You output only JSON with key angles (array). No markdown fencing."
    try:
        data = llm_svc.chat_json(system=system, user=user, temperature=0.55)
        raw = data.get("angles")
        if not isinstance(raw, list) or not raw:
            raise ValueError("no angles")
        angles: list[SocialPostAngle] = []
        for row in raw[:6]:
            if not isinstance(row, dict):
                continue
            angles.append(
                SocialPostAngle(
                    title=str(row.get("title") or "")[:200],
                    hook=str(row.get("hook") or "")[:800],
                    platform_notes=str(row.get("platform_notes") or "")[:400],
                )
            )
        if not angles:
            raise ValueError("empty angles")
        log.info("gen.social_ideas.llm_ok", count=len(angles))
        return SocialIdeaPack(angles=angles)
    except Exception as e:  # noqa: BLE001
        log.warning("gen.social_ideas.llm_failed", error=str(e))
        return _fallback(title, angle)
