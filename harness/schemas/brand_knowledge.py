"""Structured brand knowledge alongside brand.yaml (partners, programmes, library refs)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PartnerEntry(BaseModel):
    """Organisation or person the brand works with."""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    role: str = ""
    organisation: str = ""
    website: str = ""
    notes: str = ""
    sensitivity: str = Field(
        default="normal",
        description='Hint for prompts: "normal" or "high" (extra care with naming/claims).',
    )


class RecurringEvent(BaseModel):
    """Campaigns, annual events, recurring programmes."""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    timing: str = ""
    description: str = ""
    messaging_notes: str = ""


class ApprovedPhrase(BaseModel):
    """Language the brand prefers (or legal/comms-approved wording)."""

    model_config = ConfigDict(extra="ignore")

    phrase: str = ""
    context: str = ""


class PartnersProgrammeKnowledge(BaseModel):
    """Optional partners.yaml root — all keys optional for a minimal file."""

    model_config = ConfigDict(extra="ignore")

    partners: list[PartnerEntry] = Field(default_factory=list)
    recurring_events: list[RecurringEvent] = Field(default_factory=list)
    approved_language: list[ApprovedPhrase] = Field(default_factory=list)
    sensitive_context: str = ""
    programme_notes: str = ""


class BrandLibraryExcerpt(BaseModel):
    """One file under library/ surfaced into the run snapshot."""

    rel_path: str
    excerpt: str
    truncated: bool = False


class BrandKnowledgeSnapshot(BaseModel):
    """Normalised bundle stored on graph state and persisted in state_json."""

    slug: str
    structured: PartnersProgrammeKnowledge = Field(default_factory=PartnersProgrammeKnowledge)
    content_notes_text: str = ""
    content_notes_truncated: bool = False
    template_hints: dict[str, Any] = Field(default_factory=dict)
    library: list[BrandLibraryExcerpt] = Field(default_factory=list)
    library_truncated: bool = False
    loaded_paths: list[str] = Field(default_factory=list)
