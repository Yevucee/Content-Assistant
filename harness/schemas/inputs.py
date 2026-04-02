"""
Typed capture models for pipeline inputs.

All modes normalise into NormalizedContentInput before shared planning/drafting.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from harness.schemas.run_modes import RunIntent, RunMode


class IdeaInputFields(BaseModel):
    """Shared shape for manual / mixed idea slices."""

    working_title: str | None = None
    title_concept: str | None = None
    rough_idea: str | None = None
    bullet_points: list[str] = Field(default_factory=list)
    angle: str | None = None
    audience: str | None = None
    cta: str | None = None
    notes: str | None = None


class ManualIdeaInput(IdeaInputFields):
    """MODE: user-supplied idea / bullets / notes (idea-driven path)."""

    @model_validator(mode="after")
    def _non_empty(self) -> ManualIdeaInput:
        has_text = any(
            [
                (self.working_title or "").strip(),
                (self.title_concept or "").strip(),
                (self.rough_idea or "").strip(),
                (self.angle or "").strip(),
                bool(self.bullet_points),
                (self.notes or "").strip(),
            ]
        )
        if not has_text:
            raise ValueError(
                "idea input requires at least one of: working_title, title_concept, "
                "rough_idea, angle, bullet_points, or notes"
            )
        return self


class MixedIdeaInput(IdeaInputFields):
    """Idea fields inside mixed mode; may be empty when other lanes carry the run."""


class WebsiteDiscoveryInput(BaseModel):
    """MODE: limited website + optional blog URL sampling for style / opportunity analysis."""

    website_url: str | None = Field(
        default=None,
        description="Primary entry URL (homepage or landing). Required for website_discovery runs.",
    )
    brand_name: str | None = Field(
        default=None,
        description="Known brand or organisation name (helps the analyst).",
    )
    blog_urls: list[str] = Field(
        default_factory=list,
        description="Explicit blog posts, category pages, or articles to sample (capped during fetch).",
    )
    extra_notes: str | None = Field(default=None, description="Focus areas or constraints for analysis.")
    max_internal_links: int = Field(
        default=3,
        ge=0,
        le=8,
        description="Same-site links to queue from the homepage HTML (blog/news-like paths only).",
    )


class DocumentInput(BaseModel):
    """MODE 4: pasted report/brief text and/or extracted upload text (filled after upload merge)."""

    pasted_text: str | None = None
    title_hint: str | None = Field(default=None, description="Optional working title override.")
    source_label: str | None = Field(
        default=None,
        description="Human label e.g. filename or 'Q4 board brief'.",
    )
    asset_ids: list[str] = Field(default_factory=list)


class TranscriptInput(BaseModel):
    """MODE 5: pasted or uploaded transcript / meeting notes (filled after upload merge)."""

    pasted_text: str | None = None
    title_hint: str | None = None
    context_notes: str | None = Field(
        default=None,
        description="Optional: e.g. 'customer interview', 'all-hands'.",
    )
    asset_ids: list[str] = Field(default_factory=list)


class ExistingBlogStyleInput(BaseModel):
    """MODE: sample explicit blog/article URLs (and optional site entry) for style analysis."""

    site_url: str | None = Field(
        default=None,
        description="Site homepage or landing; if omitted, derived from the first blog_urls entry.",
    )
    blog_urls: list[str] = Field(
        default_factory=list,
        description="Article or listing URLs to fetch (capped by website analysis service).",
    )
    study_site: bool = Field(
        default=True,
        description="When True and site_url resolves, allow limited same-site link discovery from homepage.",
    )


class UploadedAssetRecord(BaseModel):
    """Future: stored upload metadata."""

    asset_id: str
    filename: str | None = None
    mime_type: str | None = None
    extracted_text_preview: str | None = None


class SourceBundle(BaseModel):
    """Explicit RSS/URL bundle when not using brand sources.yaml alone."""

    rss_feeds: list[str] = Field(default_factory=list)
    manual_urls: list[str] = Field(default_factory=list)


class StyleReferenceBundle(BaseModel):
    """Inferred or manual style hints."""

    from_template_slug: str | None = None
    provisional_profile: dict[str, Any] | None = None


def _mixed_lane_text_non_empty(documents: DocumentInput | None, transcript: TranscriptInput | None) -> bool:
    if documents and (documents.pasted_text or "").strip():
        return True
    if transcript and (transcript.pasted_text or "").strip():
        return True
    return False


def _idea_lane_non_empty(idea: MixedIdeaInput | None) -> bool:
    if idea is None:
        return False
    return any(
        [
            (idea.working_title or "").strip(),
            (idea.title_concept or "").strip(),
            (idea.rough_idea or "").strip(),
            (idea.angle or "").strip(),
            bool(idea.bullet_points),
            (idea.notes or "").strip(),
        ]
    )


class MixedInputBundle(BaseModel):
    """Combine idea, documents, transcript, extra URLs, and instructions into one run."""

    idea: MixedIdeaInput | None = None
    website: WebsiteDiscoveryInput | None = None
    documents: DocumentInput | None = None
    transcript: TranscriptInput | None = None
    existing_blog_style: ExistingBlogStyleInput | None = None
    sources: SourceBundle | None = None
    style: StyleReferenceBundle | None = None
    user_instructions: str | None = Field(
        default=None,
        description="Free-form editor instructions (precedence below explicit idea.angle when both set).",
    )

    @model_validator(mode="after")
    def _at_least_one_substantive_lane(self) -> MixedInputBundle:
        has_idea = _idea_lane_non_empty(self.idea)
        has_doc_tr = _mixed_lane_text_non_empty(self.documents, self.transcript)
        has_urls = bool(self.sources and (self.sources.manual_urls or self.sources.rss_feeds))
        has_notes = bool((self.user_instructions or "").strip())
        if not any([has_idea, has_doc_tr, has_urls, has_notes]):
            raise ValueError(
                "mixed input requires at least one of: idea fields, document text, transcript text, "
                "user_instructions, or sources (manual_urls / rss_feeds)"
            )
        return self


class NormalizedContentInput(BaseModel):
    """
    Canonical input to planning: one merged view after adapters run.

    Populated for idea-driven runs immediately after normalisation.
    """

    run_mode: RunMode
    run_intent: RunIntent
    run_id: str | None = None
    brand_slug: str = ""

    working_title: str = ""
    summary_for_brief: str = Field(
        default="",
        description="Plaintext nucleus: idea, bullets, notes merged for LLM context.",
    )
    angle: str = ""
    audience_hint: str = ""
    cta_hint: str = ""
    supporting_notes: str = ""
    source_item_refs: list[str] = Field(
        default_factory=list,
        description="URLs or asset ids when sources exist.",
    )
    template_profile_hints: dict[str, Any] = Field(default_factory=dict)
    source_material: dict[str, Any] = Field(
        default_factory=dict,
        description="Audit: label, paths, lengths — not secrets.",
    )
