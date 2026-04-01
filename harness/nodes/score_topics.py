"""Stage B: topic discovery (LLM + heuristic fallback)."""

from __future__ import annotations

import structlog

from harness.schemas.pipeline import PipelineStage
from harness.schemas.sources import SourceItem
from harness.services import topic_generation
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def score_topics(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    brand = state.get("brand_config_snapshot") or {}
    raw_items: list = state.get("source_items") or []
    items: list[SourceItem] = []
    for row in raw_items:
        try:
            items.append(SourceItem.model_validate(row))
        except Exception:  # noqa: BLE001
            log.warning("node.score_topics.skip_item", slug=slug)
    log.info("node.score_topics", slug=slug, sources=len(items))
    candidates = topic_generation.generate_topic_candidates(brand, items)
    return {
        "topic_candidates": [c.model_dump(mode="json") for c in candidates],
        "stage": PipelineStage.TOPICS_SCORED.value,
    }
