"""WordPress export result."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WordPressExportResult(BaseModel):
    """Outcome of draft post creation."""

    post_id: int | None = None
    link: str | None = None
    status: str = "draft"
    error_message: str | None = None
    raw_response_summary: str | None = Field(
        default=None, description="Sanitised summary for logs only"
    )
