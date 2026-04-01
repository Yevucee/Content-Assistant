"""Phase 1 pipeline graph and phase 2 WordPress export subgraph."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from harness.nodes import (
    create_editorial_brief,
    draft_article,
    export_to_wordpress_draft,
    fetch_sources,
    generate_channel_assets,
    load_brand_config,
    persist_review_item,
    review_article,
    score_topics,
    select_topic,
)
from harness.state.graph_state import GraphState


def build_phase1_graph():
    """Ingestion through review queue; ends at pending_review."""
    g = StateGraph(GraphState)
    g.add_node("load_brand_config", load_brand_config)
    g.add_node("fetch_sources", fetch_sources)
    g.add_node("score_topics", score_topics)
    g.add_node("select_topic", select_topic)
    g.add_node("create_editorial_brief", create_editorial_brief)
    g.add_node("draft_article", draft_article)
    g.add_node("review_article", review_article)
    g.add_node("generate_channel_assets", generate_channel_assets)
    g.add_node("persist_review_item", persist_review_item)

    g.set_entry_point("load_brand_config")
    g.add_edge("load_brand_config", "fetch_sources")
    g.add_edge("fetch_sources", "score_topics")
    g.add_edge("score_topics", "select_topic")
    g.add_edge("select_topic", "create_editorial_brief")
    g.add_edge("create_editorial_brief", "draft_article")
    g.add_edge("draft_article", "review_article")
    g.add_edge("review_article", "generate_channel_assets")
    g.add_edge("generate_channel_assets", "persist_review_item")
    g.add_edge("persist_review_item", END)
    return g.compile()


def build_phase2_export_graph():
    """Runs only after human approval; WordPress draft only."""
    g = StateGraph(GraphState)
    g.add_node("export_to_wordpress_draft", export_to_wordpress_draft)
    g.set_entry_point("export_to_wordpress_draft")
    g.add_edge("export_to_wordpress_draft", END)
    return g.compile()
