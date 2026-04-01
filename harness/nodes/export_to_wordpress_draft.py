"""Stage J: WordPress draft export (stub service; full in Milestone 5)."""

from __future__ import annotations

import structlog

from harness.schemas.pipeline import PipelineStage, RunPhase, RunStatus
from harness.services import wordpress as wp_service
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def export_to_wordpress_draft(state: GraphState) -> dict:
    log.info("node.export_to_wordpress_draft.stub", run_id=state.get("run_id"))
    snapshot = state.get("brand_config_snapshot") or {}
    wp_cfg = snapshot.get("wordpress") or {}
    site_url = wp_cfg.get("site_url") or "https://example.com"
    result = wp_service.create_draft_post(
        site_url=site_url,
        username="stub",
        application_password="stub",
        title=(state.get("article_draft") or {}).get("title", "Draft"),
        content=(state.get("article_draft") or {}).get("body_md", ""),
        excerpt=(state.get("metadata_package") or {}).get("excerpt", ""),
        slug=(state.get("metadata_package") or {}).get("slug", ""),
        status="draft",
    )
    return {
        "phase": RunPhase.PHASE2_EXPORT.value,
        "status": RunStatus.COMPLETED.value,
        "stage": PipelineStage.EXPORTED.value,
        "wordpress_export": result.model_dump(mode="json"),
    }
