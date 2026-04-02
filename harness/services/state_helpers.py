"""Parse graph state fragments for generation nodes."""

from __future__ import annotations

from typing import Any

from harness.schemas.sources import SourceItem
from harness.services import brand_knowledge_loader
from harness.services.brand_template import overlay_brand_dict_with_resolved_template
from harness.utils.url_normalize import normalize_url


def brand_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """
    Brand profile for LLM prompts. Merges optional brand_knowledge_snapshot into
    a single `brand_knowledge_context` string (not persisted on brand_config_snapshot).
    Applies ``resolved_brand_template`` when present (active file merged in load_brand_config).
    """
    b = dict(state.get("brand_config_snapshot") or {})
    rt = state.get("resolved_brand_template")
    if rt:
        b["resolved_brand_template"] = rt
        b = overlay_brand_dict_with_resolved_template(b)
    snap = state.get("brand_knowledge_snapshot")
    if snap:
        ctx = brand_knowledge_loader.format_knowledge_for_prompt(snap)
        if ctx:
            b["brand_knowledge_context"] = ctx
    return b


def source_items_from_state(state: dict[str, Any]) -> list[SourceItem]:
    out: list[SourceItem] = []
    for row in state.get("source_items") or []:
        try:
            out.append(SourceItem.model_validate(row))
        except Exception:  # noqa: BLE001
            continue
    return out


def numbered_sources(items: list[SourceItem], limit: int = 40) -> list[dict[str, Any]]:
    """1-based index for model prompts (explicit grounding)."""
    rows: list[dict[str, Any]] = []
    for i, it in enumerate(items[:limit], start=1):
        rows.append(
            {
                "n": i,
                "title": it.title,
                "url": str(it.url),
                "summary": (it.summary or "")[:500],
                "source_name": it.source_name,
            }
        )
    return rows


def supporting_for_topic(
    selected_topic: dict[str, Any],
    all_items: list[SourceItem],
) -> list[SourceItem | str]:
    """Map topic supporting_sources onto validated SourceItems where possible."""
    url_to_item = {normalize_url(str(s.url)): s for s in all_items}
    merged: list[SourceItem | str] = []
    seen: set[str] = set()
    for raw in selected_topic.get("supporting_sources") or []:
        if isinstance(raw, str):
            nu = normalize_url(raw)
            if nu in url_to_item:
                item = url_to_item[nu]
                key = normalize_url(str(item.url))
                if key not in seen:
                    seen.add(key)
                    merged.append(item)
            elif nu and nu not in seen:
                seen.add(nu)
                merged.append(raw)
        elif isinstance(raw, dict):
            try:
                it = SourceItem.model_validate(raw)
            except Exception:  # noqa: BLE001
                continue
            key = normalize_url(str(it.url))
            if key not in seen:
                seen.add(key)
                merged.append(it)
    return merged
