"""Aggregate pipeline state (Pydantic mirror of persisted / review payload)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from harness.schemas.content import (
    ArticleDraft,
    EditorialBrief,
    ImagePromptSet,
    LinkedInPost,
    MetadataPackage,
    ReviewWarnings,
)
from harness.schemas.sources import SourceItem
from harness.schemas.topics import TopicCandidate


class PipelineStage(str, Enum):
    """Fine-grained stage within phase 1."""

    INIT = "init"
    SOURCES_INGESTED = "sources_ingested"
    TOPICS_SCORED = "topics_scored"
    TOPIC_SELECTED = "topic_selected"
    BRIEF_READY = "brief_ready"
    DRAFT_READY = "draft_ready"
    REVIEWED = "reviewed"
    ASSETS_READY = "assets_ready"
    PENDING_REVIEW = "pending_review"
    EXPORTING = "exporting"
    EXPORTED = "exported"
    FAILED = "failed"


class RunStatus(str, Enum):
    """Coarse run lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITING_LATER = "editing_later"
    COMPLETED = "completed"
    FAILED = "failed"


class RunPhase(str, Enum):
    """Two-phase orchestration: pipeline then optional WordPress export."""

    PHASE1_PIPELINE = "phase1_pipeline"
    PHASE2_EXPORT = "phase2_export"


class PipelineRunState(BaseModel):
    """
    Typed snapshot of a run for API/review and persistence.

    LangGraph uses a parallel TypedDict in harness.state.graph_state; this model
    is used when validating JSON from the DB or returning API payloads.
    """

    run_id: UUID | str
    brand_slug: str
    phase: RunPhase = RunPhase.PHASE1_PIPELINE
    status: RunStatus = RunStatus.PENDING
    stage: PipelineStage = PipelineStage.INIT

    brand_config_snapshot: dict[str, Any] | None = None

    source_items: list[SourceItem] = Field(default_factory=list)
    topic_candidates: list[TopicCandidate] = Field(default_factory=list)
    selected_topic: TopicCandidate | None = None
    editorial_brief: EditorialBrief | None = None
    article_draft: ArticleDraft | None = None
    review_warnings: ReviewWarnings | None = None
    linkedin_post: LinkedInPost | None = None
    image_prompts: ImagePromptSet | None = None
    metadata_package: MetadataPackage | None = None

    errors: list[str] = Field(default_factory=list)
    log_refs: list[str] = Field(default_factory=list)

    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(use_enum_values=True)
