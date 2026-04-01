"""Stage G: LinkedIn, image prompts, metadata."""

from __future__ import annotations

import structlog

from harness.schemas.pipeline import PipelineStage
from harness.services import gen_image_prompts, gen_linkedin, gen_metadata
from harness.services.state_helpers import brand_snapshot
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def generate_channel_assets(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    log.info("node.generate_channel_assets", slug=slug)
    brand = brand_snapshot(state)
    draft = state.get("article_draft") or {}
    brief = state.get("editorial_brief") or {}
    li = gen_linkedin.generate_linkedin(brand, draft, brief)
    images = gen_image_prompts.generate_image_prompts(brand, draft, brief)
    meta = gen_metadata.generate_metadata(brand, draft, brief)
    return {
        "linkedin_post": li.model_dump(mode="json"),
        "image_prompts": images.model_dump(mode="json"),
        "metadata_package": meta.model_dump(mode="json"),
        "stage": PipelineStage.ASSETS_READY.value,
    }
