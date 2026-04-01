"""Source items and list configuration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class SourceItem(BaseModel):
    """Normalised item from RSS or manual URL fetch."""

    title: str
    url: HttpUrl | str
    source_id: str = ""
    source_name: str = ""
    published_at: datetime | None = None
    summary: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class SourceListConfig(BaseModel):
    """Per-brand sources: RSS feeds and static URLs."""

    rss_feeds: list[str] = Field(default_factory=list)
    manual_urls: list[str] = Field(default_factory=list)
