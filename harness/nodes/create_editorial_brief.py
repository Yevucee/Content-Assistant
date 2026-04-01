"""Stage D: editorial brief from topic + sources."""

from __future__ import annotations

import structlog

from harness.schemas.pipeline import PipelineStage
from harness.services import gen_editorial_brief
from harness.services.state_helpers import brand_snapshot, source_items_from_state
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def create_editorial_brief(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    log.info("node.create_editorial_brief", slug=slug)
    brand = brand_snapshot(state)
    items = source_items_from_state(state)
    sel = state.get("selected_topic") or {}
    brief = gen_editorial_brief.generate_editorial_brief(brand, sel, items)
    return {
        "editorial_brief": brief.model_dump(mode="json"),
        "stage": PipelineStage.BRIEF_READY.value,
    }
