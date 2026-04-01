"""Fetch and normalise RSS + manual URL sources for a brand."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
import structlog

from harness.schemas.sources import SourceItem, SourceListConfig
from harness.utils.url_normalize import normalize_url

log = structlog.get_logger(__name__)

DEFAULT_USER_AGENT = "ContentHarness/0.2 (+https://example.local; editorial ingestion)"
MAX_ENTRIES_PER_FEED = int(os.environ.get("SOURCE_RSS_MAX_ENTRIES", "25"))
MAX_TOTAL_ITEMS = int(os.environ.get("SOURCE_MAX_TOTAL_ITEMS", "80"))
FETCH_TIMEOUT = float(os.environ.get("SOURCE_FETCH_TIMEOUT", "20"))


def _http_client() -> httpx.Client:
    return httpx.Client(
        timeout=FETCH_TIMEOUT,
        headers={"User-Agent": os.environ.get("SOURCE_USER_AGENT", DEFAULT_USER_AGENT)},
        follow_redirects=True,
    )


def _entry_datetime(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key) if hasattr(entry, "get") else getattr(entry, key, None)
        if t and isinstance(t, time.struct_time):
            try:
                return datetime(
                    t.tm_year,
                    t.tm_mon,
                    t.tm_mday,
                    t.tm_hour,
                    t.tm_min,
                    t.tm_sec,
                    tzinfo=timezone.utc,
                )
            except (ValueError, TypeError):
                continue
    return None


def _extract_title_description(html: str) -> tuple[str, str]:
    html = html or ""
    title = ""
    m = re.search(
        r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    if m:
        title = unescape(m.group(1)).strip()
    if not title:
        m = re.search(r"<title[^>]*>([^<]{1,500})</title>", html, re.I | re.DOTALL)
        if m:
            title = unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    desc = ""
    m = re.search(
        r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    if m:
        desc = unescape(m.group(1)).strip()
    if not desc:
        m = re.search(
            r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
            html,
            re.I,
        )
        if m:
            desc = unescape(m.group(1)).strip()
    return title or "Untitled page", desc


def fetch_manual_url(url: str, client: httpx.Client) -> SourceItem | None:
    """GET page and derive title/summary from HTML meta/title."""
    norm = normalize_url(url)
    if not norm:
        return None
    try:
        r = client.get(norm)
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        if "html" not in ct.lower() and "text" not in ct.lower():
            log.info("source.manual.non_html", url=norm, content_type=ct)
        title, desc = _extract_title_description(r.text[:500_000])
        host = urlparse(norm).netloc or "manual"
        return SourceItem(
            title=title[:500],
            url=norm,
            source_id=f"manual:{host}",
            source_name=host,
            summary=desc[:4000],
            raw={"kind": "manual", "content_type": ct},
        )
    except Exception as e:  # noqa: BLE001
        log.warning("source.manual.failed", url=norm, error=str(e))
        return None


def fetch_rss_feed(feed_url: str, client: httpx.Client) -> list[SourceItem]:
    """Download XML and parse with feedparser; return normalised items."""
    out: list[SourceItem] = []
    try:
        r = client.get(feed_url)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("source.rss.download_failed", url=feed_url, error=str(e))
        return out

    parsed = feedparser.parse(r.text)
    feed_title = (parsed.feed.get("title") or "").strip() or urlparse(feed_url).netloc
    base_link = parsed.feed.get("link") or feed_url

    for i, entry in enumerate(parsed.entries[:MAX_ENTRIES_PER_FEED]):
        link = (entry.get("link") or "").strip()
        if not link:
            link = entry.get("id") or ""
        if link and not link.startswith(("http://", "https://")):
            link = urljoin(base_link, link)
        if not link:
            continue
        title = (entry.get("title") or "Untitled").strip()
        summary = (
            entry.get("summary")
            or entry.get("description")
            or entry.get("subtitle")
            or ""
        )
        summary = re.sub(r"<[^>]+>", " ", summary)
        summary = unescape(re.sub(r"\s+", " ", summary)).strip()[:4000]
        item = SourceItem(
            title=title[:500],
            url=normalize_url(link),
            source_id=f"rss:{feed_url}:{i}",
            source_name=feed_title[:200],
            published_at=_entry_datetime(entry),
            summary=summary,
            raw={"kind": "rss", "feed_url": feed_url},
        )
        out.append(item)
    return out


def dedupe_items(items: list[SourceItem]) -> list[SourceItem]:
    """First-wins by normalised URL."""
    seen: set[str] = set()
    uniq: list[SourceItem] = []
    for it in items:
        key = normalize_url(str(it.url))
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq


def ingest_sources(config: SourceListConfig) -> list[SourceItem]:
    """
    Fetch all RSS feeds and manual URLs, merge, dedupe, cap total count.

    Each failure is logged; ingestion continues with whatever succeeded.
    """
    collected: list[SourceItem] = []
    with _http_client() as client:
        for feed in config.rss_feeds:
            u = feed.strip()
            if not u:
                continue
            batch = fetch_rss_feed(u, client)
            log.info("source.rss.ingested", feed=u, count=len(batch))
            collected.extend(batch)

        for manual in config.manual_urls:
            u = manual.strip()
            if not u:
                continue
            item = fetch_manual_url(u, client)
            if item:
                collected.append(item)
                log.info("source.manual.ingested", url=u)
            else:
                log.info("source.manual.skipped", url=u)

    merged = dedupe_items(collected)
    if len(merged) > MAX_TOTAL_ITEMS:
        merged = merged[:MAX_TOTAL_ITEMS]
    log.info("source.ingestion.done", total=len(merged))
    return merged
