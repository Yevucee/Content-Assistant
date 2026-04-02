"""Persist source items and topic candidates for a pipeline run."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from harness.models.artifacts import RunSourceItem, RunTopicCandidate
from harness.models.generated import RunGeneratedContent


def _parse_published_at(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


async def persist_run_sources_and_topics(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    source_items: list[dict[str, Any]],
    topic_candidates: list[dict[str, Any]],
) -> None:
    """Insert normalised rows; caller commits."""
    for order, raw in enumerate(source_items):
        url = str(raw.get("url") or "")
        if not url:
            continue
        row = RunSourceItem(
            run_id=run_id,
            sort_order=order,
            title=str(raw.get("title") or "")[:2000],
            url=url[:2000],
            source_id=str(raw.get("source_id") or "")[:500],
            source_name=str(raw.get("source_name") or "")[:500],
            published_at=_parse_published_at(raw.get("published_at")),
            summary=str(raw.get("summary") or "")[:8000],
            extra_json=json.dumps(raw.get("raw") or {}, default=str, ensure_ascii=False),
        )
        session.add(row)

    sorted_topics = sorted(
        topic_candidates,
        key=lambda c: float(c.get("score", 0.0)),
        reverse=True,
    )
    for rank, raw in enumerate(sorted_topics):
        supporting = raw.get("supporting_sources") or []
        row = RunTopicCandidate(
            run_id=run_id,
            rank=rank,
            working_title=str(raw.get("working_title") or "")[:2000],
            angle=str(raw.get("angle") or "")[:8000],
            why_for_brand=str(raw.get("why_for_brand") or "")[:8000],
            score=float(raw.get("score") or 0.0),
            confidence=float(raw.get("confidence") or 0.0),
            supporting_sources_json=json.dumps(supporting, default=str, ensure_ascii=False),
        )
        session.add(row)


async def persist_run_generated_content(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    editorial_brief: dict[str, Any],
    article_draft: dict[str, Any],
    linkedin: dict[str, Any],
    image_prompts: dict[str, Any],
    metadata_package: dict[str, Any],
    review_warnings: dict[str, Any],
    channel_outputs: dict[str, Any] | None = None,
) -> None:
    """Store Milestone 3 outputs for inspection and future review UI."""
    res = await session.execute(
        select(RunGeneratedContent).where(RunGeneratedContent.run_id == run_id)
    )
    existing = res.scalar_one_or_none()
    if existing is not None:
        await session.delete(existing)
        await session.flush()

    row = RunGeneratedContent(
        run_id=run_id,
        editorial_brief_json=json.dumps(editorial_brief or {}, default=str, ensure_ascii=False),
        article_draft_json=json.dumps(article_draft or {}, default=str, ensure_ascii=False),
        linkedin_json=json.dumps(linkedin or {}, default=str, ensure_ascii=False),
        image_prompts_json=json.dumps(image_prompts or {}, default=str, ensure_ascii=False),
        metadata_json=json.dumps(metadata_package or {}, default=str, ensure_ascii=False),
        review_warnings_json=json.dumps(review_warnings or {}, default=str, ensure_ascii=False),
        channel_outputs_json=json.dumps(channel_outputs or {}, default=str, ensure_ascii=False),
    )
    session.add(row)
