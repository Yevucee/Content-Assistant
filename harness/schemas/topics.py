"""Topic discovery schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from harness.schemas.sources import SourceItem


class TopicCandidate(BaseModel):
    """One scored article opportunity."""

    working_title: str
    angle: str
    why_for_brand: str
    supporting_sources: list[SourceItem | str] = Field(default_factory=list)
    score: float = 0.0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
