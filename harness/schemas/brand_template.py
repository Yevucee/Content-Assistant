"""
Reusable brand voice / structure template.

May be loaded from YAML (BrandConfig), from disk (``brand_template.yaml``),
inferred from site/blog analysis (proposed), or merged from both.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BrandTemplatePromptSource(str, Enum):
    """Which source shaped ``resolved_brand_template`` for prompt-time merge."""

    ACTIVE_FILE = "active_file"
    BRAND_YAML_ONLY = "brand_yaml_only"


class BrandTemplateResolution(BaseModel):
    """Persisted on each run so review can see how templates were resolved."""

    prompt_template_source: BrandTemplatePromptSource
    active_template_relpath: str | None = Field(
        default=None,
        description="Relative to brands root, e.g. my_brand/brand_template.yaml",
    )
    active_file_existed_at_load: bool = False
    proposed_template_in_run: bool = False
    proposed_not_applied_to_prompts: bool = False


def merge_template_profiles(
    base: BrandTemplateProfile,
    overlay: BrandTemplateProfile,
) -> BrandTemplateProfile:
    """
    Overlay wins for non-empty strings and non-empty lists; ``extra`` dicts merge.
    ``preferred_article_length_words`` uses overlay when not None.
    """
    bd = base.model_dump()
    od = overlay.model_dump()
    merged: dict[str, Any] = dict(bd)
    for key, val in od.items():
        if key == "extra":
            merged["extra"] = {**(bd.get("extra") or {}), **(val or {})}
        elif key == "preferred_article_length_words":
            if val is not None:
                merged[key] = val
        elif isinstance(val, str):
            if val.strip():
                merged[key] = val
        elif isinstance(val, list):
            if val:
                merged[key] = list(val)
    return BrandTemplateProfile.model_validate(merged)


class BrandTemplateProfile(BaseModel):
    """Structured template used by prompts and normalisers."""

    tone_summary: str = ""
    audience: str = ""
    preferred_article_length_words: int | None = Field(
        default=None,
        description="Soft target for drafts when set.",
    )
    intro_style: str = ""
    heading_style: str = ""
    narrative_style: str = ""
    evidence_style: str = Field(default="", description="How sources/evidence are framed.")
    cta_style: str = ""
    banned_phrases: list[str] = Field(default_factory=list)
    preferred_phrases: list[str] = Field(default_factory=list)
    image_direction: str = ""
    metadata_tendencies: str = ""
    linkedin_tone: str = ""
    facebook_tone: str = ""
    instagram_tone: str = ""
    category_hints: list[str] = Field(default_factory=list)
    tag_hints: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict, description="Forward-compatible bag.")

    @classmethod
    def from_brand_config_dict(cls, brand: dict[str, Any]) -> BrandTemplateProfile:
        """Best-effort map from persisted brand_config_snapshot JSON."""
        li = brand.get("linkedin") or {}
        if not isinstance(li, dict):
            li = {}
        img = brand.get("image") or {}
        if not isinstance(img, dict):
            img = {}
        md = brand.get("metadata") or {}
        if not isinstance(md, dict):
            md = {}
        return cls(
            tone_summary=str(brand.get("tone", "")),
            audience=str(brand.get("audience", "")),
            intro_style="",
            heading_style="",
            narrative_style="",
            evidence_style="",
            cta_style=str(brand.get("cta_style", "")),
            banned_phrases=list(brand.get("banned_phrases") or []),
            preferred_phrases=[],
            image_direction=str(img.get("style_notes", "")),
            metadata_tendencies=str(md.get("title_suffix") or ""),
            linkedin_tone=str(li.get("tone_notes", "")),
            facebook_tone="",
            instagram_tone="",
            category_hints=list(md.get("default_categories") or []),
            tag_hints=[],
        )

