"""Load brand YAML into graph state."""

from __future__ import annotations

import structlog

from harness.services import brand_loader
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def load_brand_config(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    log.info("node.load_brand_config", slug=slug)
    brand, sources = brand_loader.load_brand_pair(slug)
    return {
        "brand_config_snapshot": brand.model_dump(mode="json"),
        "sources_config": sources.model_dump(mode="json"),
    }
