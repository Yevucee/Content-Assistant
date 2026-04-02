"""Normalise mode-specific capture into NormalizedContentInput + topic seed data."""

from __future__ import annotations

from typing import Any

from harness.schemas.inputs import (
    DocumentInput,
    IdeaInputFields,
    ManualIdeaInput,
    NormalizedContentInput,
    TranscriptInput,
)
from harness.schemas.run_modes import RunIntent, RunMode
from harness.schemas.topics import TopicCandidate
from harness.services import transcript_ingestion
from harness.services.upload_storage import MAX_STORED_SOURCE_CHARS


def build_summary_text(idea: IdeaInputFields) -> str:
    parts: list[str] = []
    if idea.rough_idea and idea.rough_idea.strip():
        parts.append(idea.rough_idea.strip())
    if idea.bullet_points:
        parts.append("Key points:\n- " + "\n- ".join(str(b) for b in idea.bullet_points if str(b).strip()))
    if idea.notes and idea.notes.strip():
        parts.append(f"Notes: {idea.notes.strip()}")
    return "\n\n".join(parts).strip()


def derive_working_title(idea: IdeaInputFields) -> str:
    for key in (idea.working_title, idea.title_concept):
        if key and str(key).strip():
            return str(key).strip()[:500]
    if idea.rough_idea and idea.rough_idea.strip():
        line = idea.rough_idea.strip().split("\n", 1)[0].strip()
        return (line[:200] + ("…" if len(line) > 200 else "")) if line else "Idea-driven draft"
    if idea.bullet_points:
        first = str(idea.bullet_points[0]).strip()
        if first:
            return first[:200]
    return "Idea-driven draft"


def derive_angle(idea: IdeaInputFields, brand_audience: str) -> str:
    if idea.angle and idea.angle.strip():
        return idea.angle.strip()[:4000]
    aud = idea.audience or brand_audience or ""
    base = build_summary_text(idea)
    if base:
        return f"Develop this into a clear story for {aud or 'the brand audience'}:\n\n{base[:3000]}"
    return "Develop the supplied bullets into a cohesive narrative."


def normalize_manual_idea(
    *,
    brand_slug: str,
    run_id: str | None,
    idea: ManualIdeaInput,
    run_intent: RunIntent,
    brand_snapshot: dict[str, Any],
) -> tuple[NormalizedContentInput, TopicCandidate]:
    audience_brand = str(brand_snapshot.get("audience", ""))
    audience = (idea.audience or "").strip() or audience_brand
    title = derive_working_title(idea)
    angle = derive_angle(idea, audience_brand)
    summary = build_summary_text(idea)
    why = summary[:1500] if summary else angle[:1500]

    normalized = NormalizedContentInput(
        run_mode=RunMode.IDEA_DRIVEN,
        run_intent=run_intent,
        run_id=run_id,
        brand_slug=brand_slug,
        working_title=title,
        summary_for_brief=summary or angle,
        angle=angle,
        audience_hint=audience,
        cta_hint=(idea.cta or "").strip() or str(brand_snapshot.get("cta_style", "")),
        supporting_notes=(idea.notes or "").strip(),
    )

    topic = TopicCandidate(
        working_title=title,
        angle=angle,
        why_for_brand=why or "Derived from user-supplied idea; refine with editorial pass.",
        supporting_sources=[],
        score=1.0,
        confidence=1.0,
    )
    return normalized, topic


def _cap_source_text(text: str) -> tuple[str, bool]:
    t = text.strip()
    if len(t) <= MAX_STORED_SOURCE_CHARS:
        return t, False
    return t[:MAX_STORED_SOURCE_CHARS], True


def normalize_document_material(
    *,
    brand_slug: str,
    run_id: str | None,
    doc: DocumentInput,
    run_intent: RunIntent,
    brand_snapshot: dict[str, Any],
    source_material: dict[str, object],
) -> tuple[NormalizedContentInput, TopicCandidate]:
    raw = (doc.pasted_text or "").strip()
    body, truncated = _cap_source_text(raw)
    aud = str(brand_snapshot.get("audience", ""))
    title = (
        (doc.title_hint or "").strip()
        or transcript_ingestion.first_meaningful_line(body, max_len=200)
        or "Article from source document"
    )
    label = (doc.source_label or "").strip() or "Pasted document"
    angle = (
        "Develop a clear, accurate article grounded in the supplied source material. "
        f"Audience: {aud or 'brand readers'}. Prefer faithful synthesis over speculation."
    )
    sm = dict(source_material)
    sm.update(
        {
            "kind": "document",
            "label": label,
            "text_length": len(raw),
            "truncated": truncated,
        }
    )

    normalized = NormalizedContentInput(
        run_mode=RunMode.DOCUMENT_DRIVEN,
        run_intent=run_intent,
        run_id=run_id,
        brand_slug=brand_slug,
        working_title=title[:500],
        summary_for_brief=body,
        angle=angle,
        audience_hint=aud,
        cta_hint=str(brand_snapshot.get("cta_style", "")),
        supporting_notes="",
        source_material=sm,
    )
    topic = TopicCandidate(
        working_title=title[:500],
        angle=angle[:4000],
        why_for_brand=(body[:1500] if body else angle[:1500]),
        supporting_sources=[],
        score=1.0,
        confidence=0.85,
    )
    return normalized, topic


def normalize_transcript_material(
    *,
    brand_slug: str,
    run_id: str | None,
    tr: TranscriptInput,
    run_intent: RunIntent,
    brand_snapshot: dict[str, Any],
    source_material: dict[str, object],
) -> tuple[NormalizedContentInput, TopicCandidate]:
    raw = transcript_ingestion.prepare_transcript_text(tr.pasted_text or "")
    body_full, truncated = _cap_source_text(raw)
    aud = str(brand_snapshot.get("audience", ""))

    insights = transcript_ingestion.llm_transcript_insights(
        brand_snapshot,
        body_full,
        tr.title_hint,
        tr.context_notes,
    )
    if insights:
        title = str(insights.get("suggested_title") or tr.title_hint or "").strip()
        if not title:
            title = transcript_ingestion.first_meaningful_line(body_full) or "Article from transcript"
        angle = str(insights.get("narrative_angle") or "")
        summary = str(insights.get("summary_for_brief") or body_full[:3500])
        themes = insights.get("key_themes")
        if isinstance(themes, list) and themes:
            summary = f"{summary}\n\nThemes: " + "; ".join(str(x) for x in themes[:8])
    else:
        title, angle, summary = transcript_ingestion.heuristic_transcript_angle(
            body_full,
            tr.title_hint,
            tr.context_notes,
            aud,
        )

    label = (source_material.get("label") if isinstance(source_material.get("label"), str) else "") or "Transcript"
    sm = dict(source_material)
    sm.update(
        {
            "kind": "transcript",
            "label": label,
            "text_length": len(raw),
            "truncated": truncated,
            "llm_structured": bool(insights),
        }
    )

    normalized = NormalizedContentInput(
        run_mode=RunMode.TRANSCRIPT_DRIVEN,
        run_intent=run_intent,
        run_id=run_id,
        brand_slug=brand_slug,
        working_title=title[:500],
        summary_for_brief=summary[: MAX_STORED_SOURCE_CHARS],
        angle=angle[:4000],
        audience_hint=aud,
        cta_hint=str(brand_snapshot.get("cta_style", "")),
        supporting_notes=(tr.context_notes or "").strip(),
        source_material=sm,
    )
    topic = TopicCandidate(
        working_title=title[:500],
        angle=angle[:4000],
        why_for_brand=summary[:1500],
        supporting_sources=[],
        score=1.0,
        confidence=0.8 if insights else 0.65,
    )
    return normalized, topic
