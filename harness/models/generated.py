"""Persisted phase-1 generated content + review (Milestone 3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class RunGeneratedContent(SQLModel, table=True):
    """One row per pipeline run: full review package for inspection / Milestone 4 UI."""

    __tablename__ = "run_generated_content"

    run_id: uuid.UUID = Field(foreign_key="pipeline_runs.id", primary_key=True)
    editorial_brief_json: str = "{}"
    article_draft_json: str = "{}"
    linkedin_json: str = "{}"
    image_prompts_json: str = "{}"
    metadata_json: str = "{}"
    review_warnings_json: str = "{}"
    channel_outputs_json: str = "{}"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
