"""Stage H: mark run ready for human review (DB persistence in runner)."""

from __future__ import annotations

import structlog

from harness.schemas.pipeline import PipelineStage, RunStatus
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def persist_review_item(state: GraphState) -> dict:
    log.info("node.persist_review_item", run_id=state.get("run_id"))
    return {
        "status": RunStatus.PENDING_REVIEW.value,
        "stage": PipelineStage.PENDING_REVIEW.value,
    }
