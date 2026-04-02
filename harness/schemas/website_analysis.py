"""Structured outputs for website / blog discovery runs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from harness.schemas.brand_template import BrandTemplateProfile


class FetchedPageDigest(BaseModel):
    """One page the harness fetched within explicit scope."""

    url: str
    title: str = ""
    discovered_via: str = Field(
        default="seed",
        description='How this URL entered the queue: "homepage", "blog_url", "internal_link".',
    )
    summary_excerpt: str = ""
    heading_outline: str = ""
    word_count_approx: int = 0


class ContentOpportunitySuggestion(BaseModel):
    """Editorial opportunity inferred from site patterns."""

    working_title: str
    angle: str = ""
    rationale: str = ""
    suggested_category: str | None = None


class WebsiteAnalysisPackage(BaseModel):
    """Full analysis payload persisted on the run (suggestions only — never overwrites brand YAML)."""

    target_site: str = ""
    brand_name_context: str = ""
    fetch_scope: dict[str, Any] = Field(default_factory=dict)
    pages: list[FetchedPageDigest] = Field(default_factory=list)
    proposed_brand_template: BrandTemplateProfile = Field(default_factory=BrandTemplateProfile)
    content_opportunities: list[ContentOpportunitySuggestion] = Field(default_factory=list)
    analysis_notes: list[str] = Field(default_factory=list)
    disclaimer: str = Field(
        default="Draft suggestions from limited fetches — review before adopting into brand.yaml or templates.",
    )
