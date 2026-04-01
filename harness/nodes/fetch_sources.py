"""Stage A: ingest RSS + manual URLs from brand sources.yaml."""

from __future__ import annotations

import structlog

from harness.schemas.pipeline import PipelineStage
from harness.schemas.sources import SourceListConfig
from harness.services import source_ingestion
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def fetch_sources(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    raw_cfg = state.get("sources_config") or {}
    cfg = SourceListConfig.model_validate(raw_cfg)
    log.info(
        "node.fetch_sources",
        slug=slug,
        rss=len(cfg.rss_feeds),
        manual=len(cfg.manual_urls),
    )
    items = source_ingestion.ingest_sources(cfg)
    return {
        "source_items": [i.model_dump(mode="json") for i in items],
        "stage": PipelineStage.SOURCES_INGESTED.value,
    }
