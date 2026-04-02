"""Website / blog sampling: proposed template + opportunities; no full article pipeline."""

from __future__ import annotations

import structlog

from harness.schemas.inputs import NormalizedContentInput, WebsiteDiscoveryInput
from harness.schemas.pipeline import PipelineStage
from harness.schemas.run_modes import RunIntent, RunMode
from harness.schemas.sources import SourceItem
from harness.schemas.topics import TopicCandidate
from harness.services.website_analysis import run_website_discovery_analysis
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def website_discover_and_analyze(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    raw = state.get("website_discovery_input") or {}
    inp = WebsiteDiscoveryInput.model_validate(raw)
    base_sm = dict(state.get("source_material") or {})
    run_intent_raw = state.get("run_intent") or RunIntent.BLOG_PLUS_SOCIAL.value
    try:
        run_intent = RunIntent(run_intent_raw)
    except ValueError:
        run_intent = RunIntent.BLOG_PLUS_SOCIAL

    log.info("node.website_discover_and_analyze", slug=slug, url=inp.website_url)
    package = run_website_discovery_analysis(inp)
    pkg_dump = package.model_dump(mode="json")
    tmpl_dump = package.proposed_brand_template.model_dump(mode="json")

    rm_raw = state.get("run_mode") or RunMode.WEBSITE_DISCOVERY.value
    try:
        run_mode_e = RunMode(rm_raw)
    except ValueError:
        run_mode_e = RunMode.WEBSITE_DISCOVERY

    summary_parts: list[str] = []
    for p in package.pages:
        summary_parts.append(f"## {p.title}\nURL: {p.url}\n{p.summary_excerpt[:2000]}")
    summary_body = "\n\n".join(summary_parts).strip()[:100_000]

    normalized = NormalizedContentInput(
        run_mode=run_mode_e,
        run_intent=run_intent,
        run_id=state.get("run_id"),
        brand_slug=slug,
        working_title=f"Website analysis: {package.brand_name_context or package.target_site}"[:500],
        summary_for_brief=summary_body
        or "No page bodies retrieved — see analysis notes and fetch_scope in website_analysis_package.",
        angle=(
            "Review proposed_brand_template and content_opportunities; apply via brand settings or a follow-on "
            "content run when ready."
        ),
        audience_hint=package.proposed_brand_template.audience or "",
        cta_hint=package.proposed_brand_template.cta_style or "",
        supporting_notes=(inp.extra_notes or "").strip()[:8000],
        source_material={
            **base_sm,
            "kind": "website_discovery",
            "fetch_scope": package.fetch_scope,
            "page_count": len(package.pages),
            "page_urls": [p.url for p in package.pages],
            "disclaimer": package.disclaimer,
        },
    )

    topic_candidates: list[TopicCandidate] = []
    for opp in package.content_opportunities:
        topic_candidates.append(
            TopicCandidate(
                working_title=opp.working_title[:500],
                angle=opp.angle[:4000],
                why_for_brand=opp.rationale[:2000],
                supporting_sources=[],
                score=0.85,
                confidence=0.55,
            ),
        )
    if not topic_candidates:
        topic_candidates.append(
            TopicCandidate(
                working_title="Editorial opportunities from site analysis",
                angle="See content_opportunities in website_analysis_package (or add more blog URLs and re-run).",
                why_for_brand="Thin or empty opportunity list.",
                supporting_sources=[],
                score=0.3,
                confidence=0.25,
            ),
        )

    source_rows: list[dict] = []
    for p in package.pages:
        source_rows.append(
            SourceItem(
                title=p.title[:500],
                url=p.url,
                source_name="website_sample",
                summary=p.summary_excerpt[:4000],
                raw={"discovered_via": p.discovered_via},
            ).model_dump(mode="json")
        )

    prev_res = dict(state.get("brand_template_resolution") or {})
    prev_res["proposed_template_in_run"] = True
    prev_res["proposed_not_applied_to_prompts"] = True

    return {
        "website_analysis_package": pkg_dump,
        "proposed_brand_template": tmpl_dump,
        "brand_template_resolution": prev_res,
        "normalized_input": normalized.model_dump(mode="json"),
        "topic_candidates": [t.model_dump(mode="json") for t in topic_candidates],
        "selected_topic": topic_candidates[0].model_dump(mode="json"),
        "source_items": source_rows,
        "editorial_brief": None,
        "article_draft": None,
        "review_warnings": None,
        "linkedin_post": None,
        "image_prompts": None,
        "metadata_package": None,
        "channel_output_bundle": None,
        "stage": PipelineStage.SITE_ANALYSIS_READY.value,
    }
