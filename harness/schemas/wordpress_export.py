"""Structured WordPress export records (draft-only, explicit user-triggered)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class WordPressExportAttemptStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class WordPressExportAttempt(BaseModel):
    """One export try; appended to the run journal."""

    run_id: UUID
    brand_slug: str
    status: WordPressExportAttemptStatus
    exported_at: datetime
    wordpress_post_id: int | None = None
    wordpress_post_url: str | None = None
    wordpress_site_base: str | None = Field(
        default=None, description="Sanitized base URL (no credentials)."
    )
    error_code: str | None = None
    error_message: str | None = None
    http_status: int | None = Field(default=None, description="Last HTTP status from WP REST.")
    wp_route: str = "/wp-json/wp/v2/posts"


class WordPressExportJournal(BaseModel):
    """All export attempts for a run (newest last)."""

    attempts: list[WordPressExportAttempt] = Field(default_factory=list)

    def last_succeeded(self) -> WordPressExportAttempt | None:
        for a in reversed(self.attempts):
            if a.status == WordPressExportAttemptStatus.SUCCEEDED:
                return a
        return None


class WordPressDraftPayload(BaseModel):
    """Fields sent to wp/v2/posts (draft only)."""

    title: str
    content_html: str
    excerpt: str | None = None
    slug: str | None = None


class WordPressCreateDraftResult(BaseModel):
    """Immediate outcome of the REST call (before DB journal append)."""

    ok: bool
    http_status: int | None = None
    wordpress_post_id: int | None = None
    wordpress_post_url: str | None = None
    error: str | None = None
    response_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Safe subset for logging/UI (no auth headers, no full body).",
    )

