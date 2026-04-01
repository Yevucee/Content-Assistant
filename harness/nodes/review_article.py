"""Stage F: fact/consistency + tone review."""

from __future__ import annotations

import structlog

from harness.schemas.pipeline import PipelineStage
from harness.services import review_pass
from harness.services.state_helpers import brand_snapshot, source_items_from_state
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def review_article(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    log.info("node.review_article", slug=slug)
    brand = brand_snapshot(state)
    items = source_items_from_state(state)
    article = state.get("article_draft") or {}
    brief = state.get("editorial_brief") or {}
    warnings = review_pass.run_review(brand, article, brief, items)
    return {
        "review_warnings": warnings.model_dump(mode="json"),
        "stage": PipelineStage.REVIEWED.value,
    }
