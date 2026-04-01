"""LLM editorial brief from topic + sources (with heuristic fallback)."""

from __future__ import annotations

import os
from typing import Any

import structlog

from harness.schemas.content import EditorialBrief
from harness.schemas.sources import SourceItem
from harness.services import llm as llm_svc
from harness.services.prompts_env import get_prompt_env
from harness.services.state_helpers import numbered_sources, supporting_for_topic

log = structlog.get_logger(__name__)


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").lower() in ("1", "true", "yes")


def _fallback_brief(
    brand: dict[str, Any],
    selected_topic: dict[str, Any],
    supporting: list[SourceItem | str],
) -> EditorialBrief:
    title = str(selected_topic.get("working_title") or "Editorial piece")
    return EditorialBrief(
        title=title,
        audience=str(brand.get("audience", "")),
        narrative_angle=str(selected_topic.get("angle", "")),
        key_claims=[
            str(selected_topic.get("why_for_brand", "Ground story in listed sources.")),
        ],
        supporting_sources=supporting,
        suggested_structure=["Introduction", "Context", "Analysis", "What it means", "Sources", "CTA"],
        risks_weak_points=["LLM unavailable — tighten claims against sources in human edit."],
        cta_direction=str(brand.get("cta_style", "Soft, brand-appropriate CTA.")),
    )


def _brief_from_llm_dict(
    data: dict[str, Any],
    brand: dict[str, Any],
    supporting: list[SourceItem | str],
) -> EditorialBrief | None:
    if not data.get("title"):
        return None
    kc = data.get("key_claims")
    if not isinstance(kc, list):
        kc = []
    ss = data.get("suggested_structure")
    if not isinstance(ss, list):
        ss = []
    rw = data.get("risks_weak_points")
    if not isinstance(rw, list):
        rw = []
    return EditorialBrief(
        title=str(data["title"])[:500],
        audience=str(data.get("audience") or brand.get("audience", ""))[:2000],
        narrative_angle=str(data.get("narrative_angle") or "")[:4000],
        key_claims=[str(x) for x in kc][:30],
        supporting_sources=supporting,
        suggested_structure=[str(x) for x in ss][:20],
        risks_weak_points=[str(x) for x in rw][:20],
        cta_direction=str(data.get("cta_direction") or brand.get("cta_style", ""))[:2000],
    )


def generate_editorial_brief(
    brand: dict[str, Any],
    selected_topic: dict[str, Any],
    all_sources: list[SourceItem],
) -> EditorialBrief:
    supporting = supporting_for_topic(selected_topic, all_sources)
    if _skip_llm():
        log.info("gen.brief.skip_llm")
        return _fallback_brief(brand, selected_topic, supporting)

    env = get_prompt_env()
    tmpl = env.get_template("editorial_brief.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        brand_description=str(brand.get("description", "")),
        tone=str(brand.get("tone", "")),
        audience=str(brand.get("audience", "")),
        key_themes=list(brand.get("key_themes") or []),
        banned_phrases=list(brand.get("banned_phrases") or []),
        cta_style=str(brand.get("cta_style", "")),
        working_title=str(selected_topic.get("working_title", "")),
        angle=str(selected_topic.get("angle", "")),
        why_for_brand=str(selected_topic.get("why_for_brand", "")),
        numbered_sources=numbered_sources(all_sources, limit=40),
    )
    system = "You output only compact JSON for editorial planning. No markdown wrappers."
    try:
        parsed = llm_svc.chat_json(system=system, user=user, temperature=0.35)
        brief = _brief_from_llm_dict(parsed, brand, supporting)
        if brief:
            log.info("gen.brief.llm_ok")
            return brief
    except Exception as e:  # noqa: BLE001
        log.warning("gen.brief.llm_failed", error=str(e))
    log.info("gen.brief.fallback")
    return _fallback_brief(brand, selected_topic, supporting)
