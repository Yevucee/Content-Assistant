"""Normalise transcript text and optionally infer angles via LLM."""

from __future__ import annotations

import os
import re
from typing import Any

import structlog

from harness.services import llm as llm_svc
from harness.services.prompts_env import get_prompt_env

log = structlog.get_logger(__name__)

_MAX_LLM_INPUT = 14_000


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").strip().lower() in ("1", "true", "yes")


def prepare_transcript_text(raw: str) -> str:
    t = raw.replace("\r\n", "\n").strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


def first_meaningful_line(text: str, max_len: int = 180) -> str:
    for line in text.split("\n"):
        s = line.strip()
        if len(s) > 8:
            return s[:max_len] + ("…" if len(s) > max_len else "")
    return ""


def heuristic_transcript_angle(
    transcript: str,
    title_hint: str | None,
    context_notes: str | None,
    brand_audience: str,
) -> tuple[str, str, str]:
    """(working_title, narrative_angle, summary_snippet) without LLM."""
    prep = prepare_transcript_text(transcript)
    title = (title_hint or "").strip() or first_meaningful_line(prep) or "Story from transcript"
    ctx = (context_notes or "").strip()
    angle = (
        f"Turn this material into editorial content for readers interested in {brand_audience or 'the topic'}."
        + (f" Context: {ctx}." if ctx else "")
    )
    snippet = prep[:3500]
    return title[:500], angle[:4000], snippet


def llm_transcript_insights(
    brand: dict[str, Any],
    transcript_excerpt: str,
    title_hint: str | None,
    context_notes: str | None,
) -> dict[str, Any] | None:
    if _skip_llm():
        return None
    env = get_prompt_env()
    tmpl = env.get_template("transcript_angles.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        audience=str(brand.get("audience", "")),
        brand_knowledge_context=str(brand.get("brand_knowledge_context", "")),
        title_hint=title_hint or "",
        context_notes=context_notes or "",
        transcript_excerpt=transcript_excerpt[:_MAX_LLM_INPUT],
    )
    system = "You output only JSON. No markdown fencing. Be faithful; do not invent quotes not in the transcript."
    try:
        data = llm_svc.chat_json(system=system, user=user, temperature=0.35)
        if isinstance(data, dict) and data.get("suggested_title"):
            log.info("transcript.llm_insights_ok")
            return data
    except Exception as e:  # noqa: BLE001
        log.warning("transcript.llm_insights_failed", error=str(e))
    return None
