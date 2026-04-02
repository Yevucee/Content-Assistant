"""Phase 1 pipeline graph — ingestion through review queue."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from harness.graphs.routing import route_after_brand
from harness.nodes import (
    create_editorial_brief,
    document_normalize_and_seed,
    draft_article,
    fetch_sources,
    generate_channel_assets,
    idea_normalize_and_seed,
    load_brand_config,
    mixed_normalize_and_seed,
    persist_review_item,
    review_article,
    score_topics,
    select_topic,
    transcript_normalize_and_seed,
    website_discover_and_analyze,
)
from harness.state.graph_state import GraphState


def build_phase1_graph():
    """Ingestion through review queue; ends at pending_review."""
    g = StateGraph(GraphState)
    g.add_node("load_brand_config", load_brand_config)
    g.add_node("idea_normalize_and_seed", idea_normalize_and_seed)
    g.add_node("document_normalize_and_seed", document_normalize_and_seed)
    g.add_node("transcript_normalize_and_seed", transcript_normalize_and_seed)
    g.add_node("mixed_normalize_and_seed", mixed_normalize_and_seed)
    g.add_node("website_discover_and_analyze", website_discover_and_analyze)
    g.add_node("fetch_sources", fetch_sources)
    g.add_node("score_topics", score_topics)
    g.add_node("select_topic", select_topic)
    g.add_node("create_editorial_brief", create_editorial_brief)
    g.add_node("draft_article", draft_article)
    g.add_node("review_article", review_article)
    g.add_node("generate_channel_assets", generate_channel_assets)
    g.add_node("persist_review_item", persist_review_item)

    g.set_entry_point("load_brand_config")
    g.add_conditional_edges(
        "load_brand_config",
        route_after_brand,
        {
            "idea_path": "idea_normalize_and_seed",
            "document_path": "document_normalize_and_seed",
            "transcript_path": "transcript_normalize_and_seed",
            "mixed_path": "mixed_normalize_and_seed",
            "website_path": "website_discover_and_analyze",
            "source_path": "fetch_sources",
        },
    )
    g.add_edge("website_discover_and_analyze", "persist_review_item")
    g.add_edge("idea_normalize_and_seed", "create_editorial_brief")
    g.add_edge("document_normalize_and_seed", "create_editorial_brief")
    g.add_edge("transcript_normalize_and_seed", "create_editorial_brief")
    g.add_edge("mixed_normalize_and_seed", "create_editorial_brief")
    g.add_edge("fetch_sources", "score_topics")
    g.add_edge("score_topics", "select_topic")
    g.add_edge("select_topic", "create_editorial_brief")
    g.add_edge("create_editorial_brief", "draft_article")
    g.add_edge("draft_article", "review_article")
    g.add_edge("review_article", "generate_channel_assets")
    g.add_edge("generate_channel_assets", "persist_review_item")
    g.add_edge("persist_review_item", END)
    return g.compile()
