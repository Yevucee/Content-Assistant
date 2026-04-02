"""Idea-driven path: normalise manual input and seed topic (skips fetch/score/select)."""

from __future__ import annotations

import structlog

from harness.schemas.inputs import ManualIdeaInput
from harness.schemas.pipeline import PipelineStage
from harness.schemas.run_modes import RunIntent
from harness.services.input_normalization import normalize_manual_idea
from harness.services.state_helpers import brand_snapshot
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def idea_normalize_and_seed(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    raw_idea = state.get("idea_input") or {}
    brand = brand_snapshot(state)
    run_intent_raw = state.get("run_intent") or RunIntent.BLOG_PLUS_SOCIAL.value
    try:
        run_intent = RunIntent(run_intent_raw)
    except ValueError:
        run_intent = RunIntent.BLOG_PLUS_SOCIAL

    idea = ManualIdeaInput.model_validate(raw_idea)
    log.info("node.idea_normalize_and_seed", slug=slug)

    normalized, topic = normalize_manual_idea(
        brand_slug=slug,
        run_id=state.get("run_id"),
        idea=idea,
        run_intent=run_intent,
        brand_snapshot=brand,
    )
    topic_dump = topic.model_dump(mode="json")
    return {
        "normalized_input": normalized.model_dump(mode="json"),
        "topic_candidates": [topic_dump],
        "selected_topic": topic_dump,
        "source_items": [],
        "stage": PipelineStage.TOPIC_SELECTED.value,
    }
