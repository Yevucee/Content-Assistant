"""LLM-backed topic discovery with heuristic fallback."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from harness.schemas.sources import SourceItem
from harness.schemas.topics import TopicCandidate
from harness.services import llm as llm_svc
from harness.utils.url_normalize import normalize_url

log = structlog.get_logger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPT_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",)),
    )


def _target_candidate_count(num_sources: int) -> int:
    """Between 3 and 5 inclusive, scaled lightly to source availability."""
    return min(5, max(3, num_sources or 3))


def _source_digest(items: list[SourceItem], limit: int = 36) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for it in items[:limit]:
        out.append(
            {
                "title": it.title,
                "url": str(it.url),
                "summary": (it.summary or "")[:1200],
            }
        )
    return out


def _heuristic_candidates(
    items: list[SourceItem],
    brand: dict[str, Any],
    target: int,
) -> list[TopicCandidate]:
    """Deterministic candidates from top sources when LLM unavailable."""
    name = brand.get("name", "the brand")
    themes = brand.get("key_themes") or []
    theme_tail = f" ({themes[0]})" if themes else ""
    out: list[TopicCandidate] = []
    if not items:
        base_titles = [
            f"What {name} readers should watch this week{theme_tail}",
            f"A practical takeaway for {brand.get('audience', 'your audience')}",
            f"Connecting developments to {name}'s focus areas",
        ]
        for i in range(target):
            out.append(
                TopicCandidate(
                    working_title=base_titles[i % len(base_titles)],
                    angle="Theme-led perspective without a specific external article",
                    why_for_brand="No sources ingested; placeholder angle tied to brand themes.",
                    supporting_sources=[],
                    score=0.35 - i * 0.05,
                    confidence=0.2,
                )
            )
        return out[:target]

    for i in range(min(target, len(items))):
        it = items[i]
        out.append(
            TopicCandidate(
                working_title=f"{it.title[:120]} — what it means for {name}",
                angle="Explain the signal and why it matters now",
                why_for_brand=f"Ties headline to {name}'s audience and themes (heuristic).",
                supporting_sources=[it],
                score=0.65 - i * 0.06,
                confidence=0.45,
            )
        )
    seen_titles = {c.working_title for c in out}
    j = 0
    while len(out) < target and j < len(items) * 4:
        it = items[j % len(items)]
        title = f"Synthesis: {it.title[:90]} and broader context for {name}"
        j += 1
        if title in seen_titles:
            continue
        seen_titles.add(title)
        out.append(
            TopicCandidate(
                working_title=title,
                angle="Combine multiple signals into one story",
                why_for_brand="Supports editorial breadth using the same source set.",
                supporting_sources=[it],
                score=0.5 - len(out) * 0.04,
                confidence=0.38,
            )
        )
    return out[:target]


def _coerce_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _candidates_from_llm_payload(
    data: dict[str, Any],
    items: list[SourceItem],
) -> list[TopicCandidate]:
    raw_list = data.get("candidates")
    if not isinstance(raw_list, list):
        return []
    url_map = {normalize_url(str(s.url)): s for s in items}
    out: list[TopicCandidate] = []
    for row in raw_list:
        if not isinstance(row, dict):
            continue
        urls_raw = row.get("supporting_urls") or row.get("supporting_url")
        if isinstance(urls_raw, str):
            urls_raw = [urls_raw]
        if not isinstance(urls_raw, list):
            urls_raw = []
        supporting: list[SourceItem | str] = []
        for u in urls_raw:
            nu = normalize_url(str(u))
            if nu in url_map:
                supporting.append(url_map[nu])
            elif nu:
                supporting.append(nu)
        out.append(
            TopicCandidate(
                working_title=str(row.get("working_title") or "Untitled angle").strip()[:500],
                angle=str(row.get("angle") or "").strip()[:2000],
                why_for_brand=str(row.get("why_for_brand") or "").strip()[:2000],
                supporting_sources=supporting,
                score=_coerce_float(row.get("score"), 0.5),
                confidence=_coerce_float(row.get("confidence"), 0.5),
            )
        )
    return out


def _pad_to_target(
    primary: list[TopicCandidate],
    items: list[SourceItem],
    brand: dict[str, Any],
    target: int,
) -> list[TopicCandidate]:
    """Ensure exactly `target` (3–5) rows; dedupe titles; prefer LLM order."""
    merged = list(primary)
    titles = {c.working_title for c in merged}
    if len(merged) >= target:
        merged.sort(key=lambda c: c.score, reverse=True)
        return merged[:target]

    filler = _heuristic_candidates(items, brand, target * 2)
    for c in filler:
        if c.working_title in titles:
            continue
        titles.add(c.working_title)
        merged.append(c)
        if len(merged) >= target:
            break
    merged.sort(key=lambda c: c.score, reverse=True)
    if len(merged) < target:
        extra = _heuristic_candidates(items, brand, target)
        for c in extra:
            if len(merged) >= target:
                break
            if c.working_title in titles:
                continue
            titles.add(c.working_title)
            merged.append(c)
    merged.sort(key=lambda c: c.score, reverse=True)
    return merged[:target]


def generate_topic_candidates(
    brand_snapshot: dict[str, Any],
    items: list[SourceItem],
) -> list[TopicCandidate]:
    """
    Produce 3–5 TopicCandidate instances: try LLM JSON, then trim/pad with heuristics.
    """
    target = _target_candidate_count(len(items))
    skip = os.environ.get("SKIP_TOPIC_LLM", "").lower() in ("1", "true", "yes")

    if not skip and items:
        try:
            env = _jinja_env()
            tmpl = env.get_template("topic_discovery.j2")
            user_msg = tmpl.render(
                brand_name=str(brand_snapshot.get("name", "Brand")),
                brand_description=brand_snapshot.get("description", ""),
                tone=brand_snapshot.get("tone", ""),
                audience=brand_snapshot.get("audience", ""),
                key_themes=list(brand_snapshot.get("key_themes") or []),
                banned_phrases=list(brand_snapshot.get("banned_phrases") or []),
                source_digest=_source_digest(items),
                target_count=target,
            )
            system_msg = (
                "You are an editorial strategist. Output only compact JSON per instructions — "
                "no markdown, no commentary."
            )
            parsed = llm_svc.chat_json(system=system_msg, user=user_msg, temperature=0.35)
            llm_cands = _candidates_from_llm_payload(parsed, items)
            llm_cands = sorted(llm_cands, key=lambda c: c.score, reverse=True)
            if len(llm_cands) >= 3:
                log.info("topic.generation.llm_ok", count=len(llm_cands))
                return _pad_to_target(llm_cands[:5], items, brand_snapshot, target)
            log.warning("topic.generation.llm_short", count=len(llm_cands))
            if llm_cands:
                return _pad_to_target(llm_cands, items, brand_snapshot, target)
        except Exception as e:  # noqa: BLE001
            log.warning("topic.generation.llm_failed", error=str(e))

    heur = _heuristic_candidates(items, brand_snapshot, target)
    return _pad_to_target(heur, items, brand_snapshot, target)
