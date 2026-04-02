"""Resolve BrandTemplateProfile for prompts (YAML today; inference later)."""

from __future__ import annotations

from typing import Any

from harness.schemas.brand_template import BrandTemplateProfile


def template_from_brand_snapshot(brand: dict[str, Any]) -> BrandTemplateProfile:
    return BrandTemplateProfile.from_brand_config_dict(brand)


def template_for_prompts(brand: dict[str, Any]) -> BrandTemplateProfile:
    """Prefer ``resolved_brand_template`` merged into ``brand_snapshot`` when present."""
    rt = brand.get("resolved_brand_template")
    if rt is not None:
        try:
            return BrandTemplateProfile.model_validate(rt)
        except Exception:  # noqa: BLE001
            pass
    return template_from_brand_snapshot(brand)


def overlay_brand_dict_with_resolved_template(b: dict[str, Any]) -> dict[str, Any]:
    """
    Copy scalar/list voice fields from ``resolved_brand_template`` onto the brand
    dict so Jinja prompts see active-template values without per-gen changes.
    """
    rt = b.get("resolved_brand_template")
    if not rt:
        return b
    prof = BrandTemplateProfile.model_validate(rt)
    out = dict(b)
    if prof.tone_summary.strip():
        out["tone"] = prof.tone_summary
    if prof.audience.strip():
        out["audience"] = prof.audience
    if prof.cta_style.strip():
        out["cta_style"] = prof.cta_style
    if prof.banned_phrases:
        out["banned_phrases"] = prof.banned_phrases
    li = dict(out.get("linkedin") or {})
    if prof.linkedin_tone.strip():
        li["tone_notes"] = prof.linkedin_tone
    out["linkedin"] = li
    img = dict(out.get("image") or {})
    if prof.image_direction.strip():
        img["style_notes"] = prof.image_direction
    out["image"] = img
    md = dict(out.get("metadata") or {})
    if prof.metadata_tendencies.strip():
        md["title_suffix"] = prof.metadata_tendencies
    if prof.category_hints:
        md["default_categories"] = prof.category_hints
    out["metadata"] = md
    return out
