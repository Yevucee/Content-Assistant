"""Pipeline run row — artifacts as JSON for v1 simplicity."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class PipelineRun(SQLModel, table=True):
    __tablename__ = "pipeline_runs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    brand_slug: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    phase: str = Field(default="phase1_pipeline")
    stage: str = Field(default="init")

    state_json: str = Field(default="{}")
    approval_json: str | None = Field(default=None)
    wordpress_result_json: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
