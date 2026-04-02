"""Shared narrative core between channels (planning output shape; extend over time)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CoreContentPackage(BaseModel):
    """
    Planned shared story kernel before per-channel wording.

    Idea- and source-driven runs can populate this from editorial_brief + draft;
    explicit population as a separate node is future work.
    """

    chosen_angle: str = ""
    key_claims: list[str] = Field(default_factory=list)
    narrative_core: str = Field(default="", description="Paragraph-style through-line for adapters.")
    audience: str = ""
    cta: str = ""
    brand_voice_notes: str = ""
