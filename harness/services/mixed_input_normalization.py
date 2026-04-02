"""
Merge mixed-input bundle + brand sources into NormalizedContentInput and topic seed.

Precedence (documented in merge_report.precedence):
- working_title: idea.working_title > idea.title_concept > documents.title_hint >
  transcript.title_hint > first line of grounded text > default label
- angle: idea.angle > user_instructions (as directive) > synthesised default
- audience: idea.audience > brand audience
- cta: idea.cta > brand cta_style
- summary_for_brief: labelled sections so no lane is silently dropped (truncated to cap)
"""

from __future__ import annotations

from typing import Any

from harness.schemas.inputs import MixedInputBundle, NormalizedContentInput
from harness.schemas.run_modes import RunIntent, RunMode
from harness.schemas.sources import SourceItem, SourceListConfig
from harness.schemas.topics import TopicCandidate
from harness.services import transcript_ingestion
from harness.services.input_normalization import _cap_source_text, build_summary_text, derive_angle
from harness.services import source_ingestion
from harness.utils.url_normalize import normalize_url


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        u = (u or "").strip()
        if not u:
            continue
        key = normalize_url(u)
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


def _merge_source_config(
    brand_sources: dict[str, Any],
    bundle: MixedInputBundle,
) -> SourceListConfig:
    base = SourceListConfig.model_validate(brand_sources or {})
    extra = bundle.sources
    rss = _dedupe_urls(list(base.rss_feeds) + (list(extra.rss_feeds) if extra else []))
    manual = _dedupe_urls(list(base.manual_urls) + (list(extra.manual_urls) if extra else []))
    return SourceListConfig(rss_feeds=rss, manual_urls=manual)


def _first_meaningful_from_text(body: str) -> str:
    line = transcript_ingestion.first_meaningful_line(body, max_len=200)
    return line or ""


def normalize_mixed_bundle(
    *,
    brand_slug: str,
    run_id: str | None,
    run_intent: RunIntent,
    brand_snapshot: dict[str, Any],
    bundle: MixedInputBundle,
    sources_config_snapshot: dict[str, Any],
    base_source_material: dict[str, Any],
) -> tuple[NormalizedContentInput, TopicCandidate, list[SourceItem], dict[str, Any]]:
    """Returns normalized input, topic seed, ingested source items, and merge_report."""
    aud_brand = str(brand_snapshot.get("audience", ""))
    idea = bundle.idea

    merged_cfg = _merge_source_config(sources_config_snapshot, bundle)
    source_items = source_ingestion.ingest_sources(merged_cfg)

    sections: list[tuple[str, str]] = []

    instr = (bundle.user_instructions or "").strip()
    if instr:
        sections.append(("User instructions", instr))

    idea_summary = ""
    if idea and _idea_has_text(idea):
        idea_summary = build_summary_text(idea)
        if idea_summary:
            sections.append(("Idea / bullets / notes", idea_summary))

    doc_raw = ""
    if bundle.documents and (bundle.documents.pasted_text or "").strip():
        doc_raw = (bundle.documents.pasted_text or "").strip()
        label = (bundle.documents.source_label or "").strip() or "Document"
        body_cap, trunc_d = _cap_source_text(doc_raw)
        sections.append((f"Document ({label})", body_cap))
        if trunc_d:
            sections.append(("_document_truncated", "true"))

    tr_raw = ""
    if bundle.transcript and (bundle.transcript.pasted_text or "").strip():
        tr_raw = transcript_ingestion.prepare_transcript_text(bundle.transcript.pasted_text or "")
        ctx = (bundle.transcript.context_notes or "").strip()
        head = "Transcript"
        if ctx:
            head = f"Transcript ({ctx})"
        body_cap, trunc_t = _cap_source_text(tr_raw)
        sections.append((head, body_cap))
        if trunc_t:
            sections.append(("_transcript_truncated", "true"))

    if source_items:
        lines = ["Ingested sources (titles for grounding):"]
        for i, it in enumerate(source_items[:25], start=1):
            lines.append(f"{i}. {it.title} — {it.url}")
        sections.append(("Sources snapshot", "\n".join(lines)))

    summary_full = "\n\n".join(
        f"## {title}\n{body}" for title, body in sections if not str(title).startswith("_")
    )
    summary_body, summary_trunc = _cap_source_text(summary_full)

    title, title_from = _pick_title(bundle, idea, idea_summary, doc_raw, tr_raw, aud_brand)
    angle, angle_from = _pick_angle(bundle, idea, aud_brand, doc_raw, tr_raw, bool(source_items))

    audience = ((idea.audience or "").strip() if idea else "") or aud_brand
    cta = ((idea.cta or "").strip() if idea else "") or str(brand_snapshot.get("cta_style", ""))

    supporting_bits: list[str] = []
    if idea and (idea.notes or "").strip():
        supporting_bits.append(f"Idea notes: {(idea.notes or '').strip()}")
    if bundle.transcript and (bundle.transcript.context_notes or "").strip():
        supporting_bits.append(f"Transcript context: {(bundle.transcript.context_notes or '').strip()}")
    supporting = "\n\n".join(supporting_bits)

    supporting_src: list[SourceItem | str] = list(source_items[:18])

    why_parts: list[str] = []
    if idea_summary:
        why_parts.append(idea_summary[:600])
    if doc_raw:
        why_parts.append(f"Document excerpt: {doc_raw[:400]}…" if len(doc_raw) > 400 else doc_raw)
    if tr_raw:
        why_parts.append(f"Transcript excerpt: {tr_raw[:400]}…" if len(tr_raw) > 400 else tr_raw)
    if not why_parts and source_items:
        why_parts.append(f"Primary grounding from {len(source_items)} ingested source(s).")
    why = "\n\n".join(why_parts)[:2000]

    confidence = 0.9
    if not idea_summary and not doc_raw and not tr_raw:
        confidence = 0.55 if source_items else 0.45
    elif source_items and (idea_summary or doc_raw or tr_raw):
        confidence = 0.88

    url_refs = [str(it.url) for it in source_items[:40]]

    merge_report: dict[str, Any] = {
        "precedence": {
            "working_title": title_from,
            "angle": angle_from,
            "audience": "idea.audience" if (idea and (idea.audience or "").strip()) else "brand.audience",
            "cta": "idea.cta" if (idea and (idea.cta or "").strip()) else "brand.cta_style",
        },
        "lanes_present": {
            "user_instructions": bool(instr),
            "idea": bool(idea_summary),
            "document": bool(doc_raw),
            "transcript": bool(tr_raw),
            "sources_merged_from_brand": bool(
                (sources_config_snapshot.get("manual_urls") or sources_config_snapshot.get("rss_feeds")),
            ),
            "sources_from_bundle_manual_urls": len(bundle.sources.manual_urls) if bundle.sources else 0,
            "sources_from_bundle_rss": len(bundle.sources.rss_feeds) if bundle.sources else 0,
            "fetched_source_items": len(source_items),
        },
        "sections_in_summary": [t for t, _ in sections if not str(t).startswith("_")],
        "summary_truncated": summary_trunc,
        "brand_knowledge_note": "Brand folder knowledge is loaded via brand_knowledge_snapshot / prompts (not duplicated here).",
    }

    sm = dict(base_source_material)
    sm.update(
        {
            "kind": "mixed",
            "mixed_merge_report": merge_report,
        }
    )

    normalized = NormalizedContentInput(
        run_mode=RunMode.MIXED,
        run_intent=run_intent,
        run_id=run_id,
        brand_slug=brand_slug,
        working_title=title[:500],
        summary_for_brief=summary_body,
        angle=angle[:4000],
        audience_hint=audience,
        cta_hint=cta,
        supporting_notes=supporting[:8000],
        source_item_refs=url_refs,
        source_material=sm,
    )
    topic = TopicCandidate(
        working_title=title[:500],
        angle=angle[:4000],
        why_for_brand=why or "Mixed-input editorial seed; refine in brief pass.",
        supporting_sources=supporting_src,
        score=1.0,
        confidence=confidence,
    )
    return normalized, topic, source_items, merge_report


def _idea_has_text(idea: Any) -> bool:
    return any(
        [
            (idea.working_title or "").strip(),
            (idea.title_concept or "").strip(),
            (idea.rough_idea or "").strip(),
            (idea.angle or "").strip(),
            bool(idea.bullet_points),
            (idea.notes or "").strip(),
        ]
    )


def _pick_title(
    bundle: MixedInputBundle,
    idea: Any,
    idea_summary: str,
    doc_raw: str,
    tr_raw: str,
    aud_brand: str,
) -> tuple[str, str]:
    if idea and (idea.working_title or "").strip():
        return (idea.working_title or "").strip()[:500], "idea.working_title"
    if idea and (idea.title_concept or "").strip():
        return (idea.title_concept or "").strip()[:500], "idea.title_concept"
    if bundle.documents and (bundle.documents.title_hint or "").strip():
        return (bundle.documents.title_hint or "").strip()[:500], "documents.title_hint"
    if bundle.transcript and (bundle.transcript.title_hint or "").strip():
        return (bundle.transcript.title_hint or "").strip()[:500], "transcript.title_hint"
    for blob, label in (
        (idea_summary, "idea.first_line"),
        (doc_raw, "document.first_line"),
        (tr_raw, "transcript.first_line"),
    ):
        if blob:
            hit = _first_meaningful_from_text(blob)
            if hit:
                return hit[:500], label
    if bundle.user_instructions:
        hit = _first_meaningful_from_text(bundle.user_instructions)
        if hit:
            return hit[:500], "user_instructions.first_line"
    return "Mixed-input editorial piece", "default"


def _pick_angle(
    bundle: MixedInputBundle,
    idea: Any,
    aud_brand: str,
    doc_raw: str,
    tr_raw: str,
    has_sources: bool,
) -> tuple[str, str]:
    if idea and (idea.angle or "").strip():
        return (idea.angle or "").strip()[:4000], "idea.angle"
    if idea and _idea_has_text(idea):
        derived = derive_angle(idea, aud_brand)
        return derived[:4000], "idea.derived_from_content"
    instr = (bundle.user_instructions or "").strip()
    if instr:
        base = (
            f"Editorial direction from user instructions (apply alongside pasted and sourced material).\n\n{instr}"
        )
        return base[:4000], "user_instructions"
    parts = [
        f"Develop one coherent story for {aud_brand or 'the brand audience'}, combining the supplied lanes."
    ]
    if doc_raw:
        parts.append("Ground claims in the document material where present.")
    if tr_raw:
        parts.append("Use the transcript faithfully; do not invent quotations.")
    if has_sources:
        parts.append("Cite ingested URLs where factual claims depend on them.")
    return " ".join(parts)[:4000], "synthesised_default"
