"""Editorial content artifacts."""

from __future__ import annotations

from pydantic import BaseModel, Field

from harness.schemas.sources import SourceItem


class EditorialBrief(BaseModel):
    """Structured brief before drafting."""

    title: str
    audience: str = ""
    narrative_angle: str = ""
    key_claims: list[str] = Field(default_factory=list)
    supporting_sources: list[SourceItem | str] = Field(default_factory=list)
    suggested_structure: list[str] = Field(default_factory=list)
    risks_weak_points: list[str] = Field(default_factory=list)
    cta_direction: str = ""


class ArticleDraft(BaseModel):
    """Blog draft body (markdown in v1)."""

    title: str
    body_md: str = ""
    word_count: int | None = None


class ReviewFlag(BaseModel):
    """Single consistency or tone flag."""

    code: str
    message: str
    severity: str = "warning"  # info | warning | error
    claim_or_excerpt: str | None = None


class ReviewWarnings(BaseModel):
    """Output of fact/consistency review pass."""

    unsupported_claims: list[ReviewFlag] = Field(default_factory=list)
    tone_flags: list[ReviewFlag] = Field(default_factory=list)
    other_notes: list[str] = Field(default_factory=list)


class LinkedInPost(BaseModel):
    """Companion LinkedIn copy."""

    text: str
    hashtags: list[str] = Field(default_factory=list)


class ImagePromptSet(BaseModel):
    """Image generation prompts."""

    prompts: list[str] = Field(default_factory=list)
    style_notes: str = ""


class MetadataPackage(BaseModel):
    """Publishing metadata package."""

    slug: str = ""
    meta_title: str = ""
    meta_description: str = ""
    excerpt: str = ""
    alt_text_suggestion: str = ""
    tags: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
