"""TypedDict state for LangGraph pipelines."""

from __future__ import annotations

import uuid
from operator import add
from typing import Annotated, Any, Optional, TypedDict

from harness.schemas.pipeline import PipelineStage, RunPhase, RunStatus


class GraphState(TypedDict, total=False):
    """Mutable pipeline state passed between nodes; merge updates per key."""

    run_id: str
    brand_slug: str
    phase: str
    status: str
    stage: str

    brand_config_snapshot: dict[str, Any]
    sources_config: dict[str, Any]

    source_items: list[dict[str, Any]]
    topic_candidates: list[dict[str, Any]]
    selected_topic: Optional[dict[str, Any]]
    editorial_brief: Optional[dict[str, Any]]
    article_draft: Optional[dict[str, Any]]
    review_warnings: Optional[dict[str, Any]]
    linkedin_post: Optional[dict[str, Any]]
    image_prompts: Optional[dict[str, Any]]
    metadata_package: Optional[dict[str, Any]]

    errors: Annotated[list[str], add]
    wordpress_export: Optional[dict[str, Any]]


def new_run_id() -> str:
    """String UUID for runs (JSON-safe)."""
    return str(uuid.uuid4())


def initial_graph_state(run_id: str, brand_slug: str) -> GraphState:
    """Starting state for phase 1."""
    return {
        "run_id": run_id,
        "brand_slug": brand_slug,
        "phase": RunPhase.PHASE1_PIPELINE.value,
        "status": RunStatus.RUNNING.value,
        "stage": PipelineStage.INIT.value,
        "source_items": [],
        "topic_candidates": [],
        "selected_topic": None,
        "editorial_brief": None,
        "article_draft": None,
        "review_warnings": None,
        "linkedin_post": None,
        "image_prompts": None,
        "metadata_package": None,
        "errors": [],
        "wordpress_export": None,
    }
