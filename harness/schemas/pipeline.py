"""Aggregate pipeline enums (stage / status / phase)."""

from __future__ import annotations

from enum import Enum


class PipelineStage(str, Enum):
    """Fine-grained stage within phase 1."""

    INIT = "init"
    SITE_ANALYSIS_READY = "site_analysis_ready"
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
    """Run `phase` field; production content uses ``phase1_pipeline`` throughout the graph."""

    PHASE1_PIPELINE = "phase1_pipeline"
    PHASE2_EXPORT = "phase2_export"  # legacy enum value; WordPress is not a LangGraph phase
