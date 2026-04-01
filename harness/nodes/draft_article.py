"""Stage E: article draft (markdown)."""

from __future__ import annotations

import structlog

from harness.schemas.pipeline import PipelineStage
from harness.services import gen_article
from harness.services.state_helpers import brand_snapshot, source_items_from_state
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def draft_article(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    log.info("node.draft_article", slug=slug)
    brand = brand_snapshot(state)
    items = source_items_from_state(state)
    brief = state.get("editorial_brief") or {}
    draft = gen_article.generate_article(brand, brief, items)
    return {
        "article_draft": draft.model_dump(mode="json"),
        "stage": PipelineStage.DRAFT_READY.value,
    }
