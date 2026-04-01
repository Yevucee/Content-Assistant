"""Stage C: pick highest-scoring candidate automatically (v1)."""

from __future__ import annotations

import structlog

from harness.schemas.pipeline import PipelineStage
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def select_topic(state: GraphState) -> dict:
    log.info("node.select_topic", slug=state.get("brand_slug"))
    cands = list(state.get("topic_candidates") or [])
    cands.sort(key=lambda c: float(c.get("score", 0.0)), reverse=True)
    best = cands[0] if cands else None
    return {
        "topic_candidates": cands,
        "selected_topic": best,
        "stage": PipelineStage.TOPIC_SELECTED.value,
    }
