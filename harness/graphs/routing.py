"""Conditional edges for unified pipeline entry paths."""

from __future__ import annotations

from typing import Literal

from harness.schemas.run_modes import RunMode
from harness.state.graph_state import GraphState


def route_after_brand(
    state: GraphState,
) -> Literal[
    "idea_path",
    "document_path",
    "transcript_path",
    "mixed_path",
    "website_path",
    "source_path",
]:
    mode = state.get("run_mode") or RunMode.SOURCE_DRIVEN.value
    if mode == RunMode.IDEA_DRIVEN.value:
        return "idea_path"
    if mode == RunMode.DOCUMENT_DRIVEN.value:
        return "document_path"
    if mode == RunMode.TRANSCRIPT_DRIVEN.value:
        return "transcript_path"
    if mode == RunMode.MIXED.value:
        return "mixed_path"
    if mode in (RunMode.WEBSITE_DISCOVERY.value, RunMode.EXISTING_BLOG_STYLE.value):
        return "website_path"
    return "source_path"
