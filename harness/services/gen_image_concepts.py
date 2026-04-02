"""Structured image concepts + prompts (generation stays manual for now)."""

from __future__ import annotations

import os
from typing import Any

import structlog

from harness.schemas.channel_outputs import ImageConcept
from harness.services import llm as llm_svc
from harness.services.prompts_env import get_prompt_env

log = structlog.get_logger(__name__)


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").lower() in ("1", "true", "yes")


def _fallback(brand: dict[str, Any], title: str, angle: str) -> list[ImageConcept]:
    img = brand.get("image") or {}
    if not isinstance(img, dict):
        img = {}
    style = str(img.get("style_notes", "clean editorial"))
    ar = str(img.get("aspect_ratio", "16:9"))
    return [
        ImageConcept(
            concept=f"Hero visual for: {title}",
            prompt_text=f"Editorial photograph, {style}, no text, theme: {angle[:120]}",
            mood="professional",
            aspect_ratio_hint=ar,
            signage_notes="Avoid text in frame unless subtle logo.",
        )
    ]


def generate_image_concepts(
    brand: dict[str, Any],
    article: dict[str, Any],
    brief: dict[str, Any],
) -> list[ImageConcept]:
    title = str(article.get("title") or brief.get("title") or "Article")
    angle = str(brief.get("narrative_angle", ""))

    if _skip_llm():
        log.info("gen.image_concepts.skip_llm")
        return _fallback(brand, title, angle)

    img = brand.get("image") or {}
    if not isinstance(img, dict):
        img = {}
    env = get_prompt_env()
    tmpl = env.get_template("image_concepts.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        image_style=str(img.get("style_notes", "")),
        aspect_ratio=str(img.get("aspect_ratio", "16:9")),
        brand_knowledge_context=str(brand.get("brand_knowledge_context", "")),
        article_title=title,
        narrative_angle=angle,
    )
    system = "You output only JSON. No markdown fencing."
    try:
        data = llm_svc.chat_json(system=system, user=user, temperature=0.55)
        raw = data.get("concepts")
        if not isinstance(raw, list) or not raw:
            raise ValueError("no concepts")
        out: list[ImageConcept] = []
        for row in raw[:6]:
            if not isinstance(row, dict):
                continue
            out.append(
                ImageConcept(
                    concept=str(row.get("concept") or "")[:500],
                    prompt_text=str(row.get("prompt_text") or "")[:4000],
                    mood=str(row.get("mood") or "")[:200],
                    aspect_ratio_hint=str(row.get("aspect_ratio_hint") or "")[:80],
                    signage_notes=str(row.get("signage_notes") or "")[:500],
                )
            )
        if not out:
            raise ValueError("empty concepts")
        log.info("gen.image_concepts.llm_ok", count=len(out))
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("gen.image_concepts.llm_failed", error=str(e))
        return _fallback(brand, title, angle)
