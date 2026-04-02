"""Mixed-input path: merge lanes + ingest sources, then seed topic for shared brief/draft."""

from __future__ import annotations

import structlog

from harness.schemas.inputs import MixedInputBundle
from harness.schemas.pipeline import PipelineStage
from harness.schemas.run_modes import RunIntent
from harness.services.mixed_input_normalization import normalize_mixed_bundle
from harness.services.state_helpers import brand_snapshot
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def mixed_normalize_and_seed(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    raw = state.get("mixed_input") or {}
    bundle = MixedInputBundle.model_validate(raw)
    brand = brand_snapshot(state)
    sources_cfg = state.get("sources_config") or {}
    base_sm = dict(state.get("source_material") or {})
    run_intent_raw = state.get("run_intent") or RunIntent.BLOG_PLUS_SOCIAL.value
    try:
        run_intent = RunIntent(run_intent_raw)
    except ValueError:
        run_intent = RunIntent.BLOG_PLUS_SOCIAL

    log.info("node.mixed_normalize_and_seed", slug=slug)
    normalized, topic, items, _merge_report = normalize_mixed_bundle(
        brand_slug=slug,
        run_id=state.get("run_id"),
        run_intent=run_intent,
        brand_snapshot=brand,
        bundle=bundle,
        sources_config_snapshot=sources_cfg,
        base_source_material=base_sm,
    )
    topic_dump = topic.model_dump(mode="json")
    nid = normalized.model_dump(mode="json")
    return {
        "normalized_input": nid,
        "source_material": nid.get("source_material") or normalized.source_material,
        "topic_candidates": [topic_dump],
        "selected_topic": topic_dump,
        "source_items": [i.model_dump(mode="json") for i in items],
        "stage": PipelineStage.TOPIC_SELECTED.value,
    }
