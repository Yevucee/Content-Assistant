"""Transcript-driven path: normalise transcript into topic + brief seed."""

from __future__ import annotations

import structlog

from harness.schemas.inputs import TranscriptInput
from harness.schemas.pipeline import PipelineStage
from harness.schemas.run_modes import RunIntent
from harness.services.input_normalization import normalize_transcript_material
from harness.services.state_helpers import brand_snapshot
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def transcript_normalize_and_seed(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    raw_tr = state.get("transcript_input") or {}
    brand = brand_snapshot(state)
    base_sm = dict(state.get("source_material") or {})
    run_intent_raw = state.get("run_intent") or RunIntent.BLOG_PLUS_SOCIAL.value
    try:
        run_intent = RunIntent(run_intent_raw)
    except ValueError:
        run_intent = RunIntent.BLOG_PLUS_SOCIAL

    tr = TranscriptInput.model_validate(raw_tr)
    log.info("node.transcript_normalize_and_seed", slug=slug)

    normalized, topic = normalize_transcript_material(
        brand_slug=slug,
        run_id=state.get("run_id"),
        tr=tr,
        run_intent=run_intent,
        brand_snapshot=brand,
        source_material=base_sm,
    )
    topic_dump = topic.model_dump(mode="json")
    nid = normalized.model_dump(mode="json")
    return {
        "normalized_input": nid,
        "source_material": nid.get("source_material") or normalized.source_material,
        "topic_candidates": [topic_dump],
        "selected_topic": topic_dump,
        "source_items": [],
        "stage": PipelineStage.TOPIC_SELECTED.value,
    }
