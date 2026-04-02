"""Stage E: article draft (markdown)."""

from __future__ import annotations

import structlog

from harness.schemas.content import ArticleDraft
from harness.schemas.pipeline import PipelineStage
from harness.schemas.run_modes import RunIntent
from harness.services import gen_article
from harness.services.state_helpers import brand_snapshot, source_items_from_state
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def draft_article(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    intent = state.get("run_intent") or RunIntent.BLOG_PLUS_SOCIAL.value
    log.info("node.draft_article", slug=slug, intent=intent)
    brand = brand_snapshot(state)
    items = source_items_from_state(state)
    brief = state.get("editorial_brief") or {}

    if intent == RunIntent.SOCIAL_ONLY.value:
        kc = brief.get("key_claims") or []
        kc_txt = "\n".join(f"- {x}" for x in kc[:8]) if isinstance(kc, list) else ""
        stub_body = (
            f"_(Social-only run — expand later or ignore.)_\n\n"
            f"## {brief.get('title', 'Summary')}\n\n"
            f"{brief.get('narrative_angle', '')}\n\n{kc_txt}"
        )
        draft = ArticleDraft(
            title=str(brief.get("title") or "Social package"),
            body_md=stub_body[:8000],
            word_count=len(stub_body.split()),
        )
    else:
        draft = gen_article.generate_article(brand, brief, items)
    return {
        "article_draft": draft.model_dump(mode="json"),
        "stage": PipelineStage.DRAFT_READY.value,
    }
