"""Per-run persisted source items and topic candidates (Milestone 2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class RunSourceItem(SQLModel, table=True):
    __tablename__ = "run_source_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="pipeline_runs.id", index=True)
    sort_order: int = 0
    title: str = ""
    url: str = Field(index=True)
    source_id: str = ""
    source_name: str = ""
    published_at: datetime | None = None
    summary: str = ""
    extra_json: str = "{}"


class RunTopicCandidate(SQLModel, table=True):
    __tablename__ = "run_topic_candidates"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="pipeline_runs.id", index=True)
    rank: int = Field(default=0, index=True)
    working_title: str = ""
    angle: str = ""
    why_for_brand: str = ""
    score: float = 0.0
    confidence: float = 0.0
    supporting_sources_json: str = "[]"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
