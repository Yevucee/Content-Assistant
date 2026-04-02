"""Image prompt set generation."""

from __future__ import annotations

import os
from typing import Any

import structlog

from harness.schemas.content import ImagePromptSet
from harness.services import llm as llm_svc
from harness.services.prompts_env import get_prompt_env

log = structlog.get_logger(__name__)


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").lower() in ("1", "true", "yes")


def _fallback_images(brand: dict[str, Any], title: str, brief_angle: str) -> ImagePromptSet:
    img = brand.get("image") or {}
    if not isinstance(img, dict):
        img = {}
    style = str(img.get("style_notes", "clean editorial"))
    return ImagePromptSet(
        prompts=[
            f"Wide editorial photograph inspired by: {title}. Style: {style}. No text in image.",
            f"Abstract visual metaphor for: {brief_angle[:120]}. {style}",
        ],
        style_notes=style,
    )


def generate_image_prompts(
    brand: dict[str, Any],
    article: dict[str, Any],
    brief: dict[str, Any],
) -> ImagePromptSet:
    title = str(article.get("title") or brief.get("title") or "Article")
    angle = str(brief.get("narrative_angle", ""))
    if _skip_llm():
        log.info("gen.images.skip_llm")
        return _fallback_images(brand, title, angle)

    img = brand.get("image") or {}
    if not isinstance(img, dict):
        img = {}
    env = get_prompt_env()
    tmpl = env.get_template("image_prompts.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        image_style_notes=str(img.get("style_notes", "")),
        aspect_ratio=str(img.get("aspect_ratio", "16:9")),
        negative_prompts=list(img.get("negative_prompts") or []),
        brand_knowledge_context=str(brand.get("brand_knowledge_context", "")),
        article_title=title,
        brief_angle=angle[:800],
    )
    system = "You output only JSON for image prompts. No markdown fencing."
    try:
        data = llm_svc.chat_json(system=system, user=user, temperature=0.5)
        prompts_raw = data.get("prompts")
        if not isinstance(prompts_raw, list) or not prompts_raw:
            raise ValueError("no prompts")
        prompts = [str(p).strip() for p in prompts_raw if str(p).strip()][:4]
        notes = str(data.get("style_notes") or img.get("style_notes") or "")
        log.info("gen.images.llm_ok", count=len(prompts))
        return ImagePromptSet(prompts=prompts, style_notes=notes[:4000])
    except Exception as e:  # noqa: BLE001
        log.warning("gen.images.llm_failed", error=str(e))
        return _fallback_images(brand, title, angle)
