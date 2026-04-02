"""Editorial QA: LLM review plus deterministic brand/source checks."""

from __future__ import annotations

import os
import re
from typing import Any

import structlog

from harness.schemas.content import ReviewFlag, ReviewWarnings
from harness.schemas.sources import SourceItem
from harness.services import llm as llm_svc
from harness.services.prompts_env import get_prompt_env
from harness.services.state_helpers import numbered_sources

log = structlog.get_logger(__name__)


def _skip_llm() -> bool:
    return os.environ.get("SKIP_CONTENT_LLM", "").lower() in ("1", "true", "yes")


def _scan_banned_phrases(article_md: str, phrases: list[str]) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    lower = article_md.casefold()
    for p in phrases:
        ph = str(p).strip()
        if not ph:
            continue
        if ph.casefold() in lower:
            flags.append(
                ReviewFlag(
                    code="BANNED-PHRASE",
                    message=f"Draft may contain banned phrase: {ph}",
                    severity="warning",
                    claim_or_excerpt=ph[:200],
                )
            )
    return flags


def _check_sources_section(article_md: str) -> list[ReviewFlag]:
    if "## sources consulted" in article_md.casefold():
        return []
    return [
        ReviewFlag(
            code="SOURCES-SECTION",
            message="Missing or non-standard '## Sources consulted' section.",
            severity="warning",
            claim_or_excerpt=None,
        )
    ]


def _weak_bracket_cites(article_md: str, num_sources: int) -> list[ReviewFlag]:
    if num_sources == 0:
        return []
    count = len(re.findall(r"\[\d+\]", article_md))
    if count < 2 and num_sources >= 2:
        return [
            ReviewFlag(
                code="GROUND-CITE",
                message="Few bracket-style [n] source references vs number of available sources.",
                severity="info",
                claim_or_excerpt=None,
            ),
        ]
    return []


def _parse_review_json(data: dict[str, Any]) -> tuple[list[ReviewFlag], list[ReviewFlag], list[str]]:
    uc: list[ReviewFlag] = []
    tf: list[ReviewFlag] = []
    notes: list[str] = []

    for row in data.get("unsupported_claims") or []:
        if not isinstance(row, dict):
            continue
        uc.append(
            ReviewFlag(
                code=str(row.get("code") or "CLAIM"),
                message=str(row.get("message") or "")[:2000],
                severity=str(row.get("severity") or "warning")[:16],
                claim_or_excerpt=(
                    str(row.get("claim_or_excerpt"))[:500] if row.get("claim_or_excerpt") else None
                ),
            )
        )
    for row in data.get("tone_flags") or []:
        if not isinstance(row, dict):
            continue
        tf.append(
            ReviewFlag(
                code=str(row.get("code") or "TONE"),
                message=str(row.get("message") or "")[:2000],
                severity=str(row.get("severity") or "warning")[:16],
                claim_or_excerpt=(
                    str(row.get("claim_or_excerpt"))[:500] if row.get("claim_or_excerpt") else None
                ),
            )
        )
    for n in data.get("other_notes") or []:
        if isinstance(n, str) and n.strip():
            notes.append(n.strip()[:2000])
    return uc, tf, notes


def run_review(
    brand: dict[str, Any],
    article: dict[str, Any],
    brief: dict[str, Any],
    all_sources: list[SourceItem],
) -> ReviewWarnings:
    body = str(article.get("body_md") or "")
    title = str(article.get("title") or "")
    banned = list(brand.get("banned_phrases") or [])

    det_ground = _check_sources_section(body) + _weak_bracket_cites(body, len(all_sources))
    det_tone = _scan_banned_phrases(body, banned)

    if _skip_llm():
        log.info("gen.review.skip_llm")
        return ReviewWarnings(
            unsupported_claims=det_ground[:80],
            tone_flags=det_tone[:40],
            other_notes=["LLM review skipped (SKIP_CONTENT_LLM); deterministic checks only."],
        )

    env = get_prompt_env()
    tmpl = env.get_template("review_pass.j2")
    user = tmpl.render(
        brand_name=str(brand.get("name", "Brand")),
        tone=str(brand.get("tone", "")),
        banned_phrases=banned,
        brand_knowledge_context=str(brand.get("brand_knowledge_context", "")),
        article_title=title,
        article_body=body[:50_000],
        numbered_sources=numbered_sources(all_sources, limit=40),
        key_claims=list(brief.get("key_claims") or []),
    )
    system = "You output only JSON for the review object. No markdown fencing."
    uc: list[ReviewFlag] = []
    tf: list[ReviewFlag] = []
    notes: list[str] = []

    try:
        data = llm_svc.chat_json(system=system, user=user, temperature=0.2)
        uc, tf, notes = _parse_review_json(data)
        log.info(
            "gen.review.llm_ok",
            unsupported=len(uc),
            tone=len(tf),
            notes=len(notes),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("gen.review.llm_failed", error=str(e))
        notes.append("LLM review failed; deterministic checks still apply.")

    uc = det_ground + uc
    tf = det_tone + tf

    return ReviewWarnings(
        unsupported_claims=uc[:100],
        tone_flags=tf[:100],
        other_notes=notes[:50],
    )
