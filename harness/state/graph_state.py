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
    brand_knowledge_snapshot: dict[str, Any]
    active_brand_template: Optional[dict[str, Any]]
    resolved_brand_template: Optional[dict[str, Any]]
    brand_template_resolution: Optional[dict[str, Any]]

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

    run_mode: str
    run_intent: str
    idea_input: Optional[dict[str, Any]]
    normalized_input: Optional[dict[str, Any]]
    channel_output_bundle: Optional[dict[str, Any]]
    document_input: Optional[dict[str, Any]]
    transcript_input: Optional[dict[str, Any]]
    mixed_input: Optional[dict[str, Any]]
    website_discovery_input: Optional[dict[str, Any]]
    website_analysis_package: Optional[dict[str, Any]]
    proposed_brand_template: Optional[dict[str, Any]]
    source_material: Optional[dict[str, Any]]


def new_run_id() -> str:
    """String UUID for runs (JSON-safe)."""
    return str(uuid.uuid4())


def initial_graph_state(
    run_id: str,
    brand_slug: str,
    *,
    run_mode: str | None = None,
    run_intent: str | None = None,
    idea_input: dict[str, Any] | None = None,
    document_input: dict[str, Any] | None = None,
    transcript_input: dict[str, Any] | None = None,
    mixed_input: dict[str, Any] | None = None,
    website_discovery_input: dict[str, Any] | None = None,
    source_material: dict[str, Any] | None = None,
) -> GraphState:
    """Starting state for phase 1."""
    from harness.schemas.run_modes import DEFAULT_RUN_INTENT, DEFAULT_RUN_MODE

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
        "active_brand_template": None,
        "resolved_brand_template": None,
        "brand_template_resolution": None,
        "run_mode": run_mode or DEFAULT_RUN_MODE.value,
        "run_intent": run_intent or DEFAULT_RUN_INTENT.value,
        "idea_input": idea_input,
        "normalized_input": None,
        "channel_output_bundle": None,
        "document_input": document_input,
        "transcript_input": transcript_input,
        "mixed_input": mixed_input,
        "website_discovery_input": website_discovery_input,
        "source_material": source_material or {},
    }
