"""Load brand YAML into graph state."""

from __future__ import annotations

import structlog

from harness.schemas.brand_template import (
    BrandTemplateProfile,
    BrandTemplatePromptSource,
    BrandTemplateResolution,
    merge_template_profiles,
)
from harness.services import brand_loader
from harness.services import brand_knowledge_loader
from harness.services import brand_template_storage
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def load_brand_config(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    log.info("node.load_brand_config", slug=slug)
    brand, sources = brand_loader.load_brand_pair(slug)
    knowledge_snapshot = brand_knowledge_loader.load_brand_knowledge_snapshot(slug)
    base_prof = BrandTemplateProfile.from_brand_config_dict(brand.model_dump(mode="json"))
    active_prof: BrandTemplateProfile | None
    load_err: str | None
    active_prof, load_err = brand_template_storage.load_active_brand_template_optional(slug)
    err_updates: dict = {}
    if load_err:
        err_updates = {
            "errors": [
                f"Invalid or unreadable brands/{slug}/brand_template.yaml: {load_err}. "
                "Using brand.yaml only until the file is fixed.",
            ],
        }
        active_prof = None

    merged = merge_template_profiles(base_prof, active_prof) if active_prof is not None else base_prof
    rel = f"{slug}/brand_template.yaml" if active_prof is not None else None
    resolution = BrandTemplateResolution(
        prompt_template_source=(
            BrandTemplatePromptSource.ACTIVE_FILE if active_prof is not None else BrandTemplatePromptSource.BRAND_YAML_ONLY
        ),
        active_template_relpath=rel,
        active_file_existed_at_load=active_prof is not None,
    )
    return {
        "brand_config_snapshot": brand.model_dump(mode="json"),
        "sources_config": sources.model_dump(mode="json"),
        "brand_knowledge_snapshot": knowledge_snapshot,
        "active_brand_template": active_prof.model_dump(mode="json") if active_prof is not None else None,
        "resolved_brand_template": merged.model_dump(mode="json"),
        "brand_template_resolution": resolution.model_dump(mode="json"),
        **err_updates,
    }
