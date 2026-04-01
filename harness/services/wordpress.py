"""WordPress REST API client — draft posts only, Application Password auth."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from harness.schemas.brand import BrandConfig, WordPressSettings
from harness.schemas.wordpress_export import WordPressCreateDraftResult, WordPressDraftPayload

log = structlog.get_logger(__name__)


class WordPressConfigError(ValueError):
    """Missing or invalid WordPress configuration (no secrets logged)."""


@dataclass(frozen=True)
class ResolvedWordPressCredentials:
    site_base: str
    username: str
    application_password: str


def normalize_site_base(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        raise WordPressConfigError("WordPress site_url is empty.")
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    parsed = urlparse(u)
    if not parsed.netloc:
        raise WordPressConfigError("WordPress site_url has no host.")
    return u


def resolve_wordpress_credentials(
    brand: BrandConfig,
    *,
    environ: dict[str, str] | None = None,
) -> ResolvedWordPressCredentials:
    """Read site URL from brand YAML; secrets from env vars named in YAML."""
    import os

    env = environ if environ is not None else os.environ
    wp: WordPressSettings | None = brand.wordpress
    if wp is None:
        raise WordPressConfigError(
            f"WordPress is not configured for brand {brand.slug!r} (add wordpress: to brand.yaml)."
        )
    base = normalize_site_base(wp.site_url)
    user_key = (wp.username_env or "").strip()
    pass_key = (wp.application_password_env or "").strip()
    if not user_key or not pass_key:
        raise WordPressConfigError("WordPress env var names are missing in brand.yaml.")
    username = (env.get(user_key) or "").strip()
    password = (env.get(pass_key) or "").strip().replace(" ", "")
    if not username or not password:
        raise WordPressConfigError(
            f"WordPress credentials are not set (check env vars {user_key} and {pass_key})."
        )
    return ResolvedWordPressCredentials(
        site_base=base, username=username, application_password=password
    )


_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify_for_wordpress(raw: str | None, max_len: int = 180) -> str | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip().lower().replace("_", "-")
    s = _NON_SLUG.sub("-", s).strip("-")
    if not s:
        return None
    return s[:max_len]


def body_md_to_basic_html(body_md: str) -> str:
    """Escape and wrap paragraphs; no raw HTML passthrough from drafts."""
    text = (body_md or "").strip()
    if not text:
        return "<p></p>"
    blocks = text.split("\n\n")
    parts: list[str] = []
    for block in blocks:
        inner = html.escape(block.strip(), quote=False)
        inner = inner.replace("\n", "<br />\n")
        parts.append(f"<p>{inner}</p>")
    return "\n".join(parts)


def draft_payload_from_state(
    *,
    brand_slug: str,
    article: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    selected_topic: dict[str, Any] | None,
) -> WordPressDraftPayload:
    title = ""
    if article and article.get("title"):
        title = str(article["title"]).strip()
    if not title and metadata and metadata.get("meta_title"):
        title = str(metadata["meta_title"]).strip()
    if not title and selected_topic and selected_topic.get("working_title"):
        title = str(selected_topic["working_title"]).strip()
    if not title:
        title = f"Draft ({brand_slug})"

    body_md = ""
    if article and article.get("body_md"):
        body_md = str(article["body_md"])
    content_html = body_md_to_basic_html(body_md)

    excerpt = None
    if metadata:
        for key in ("excerpt", "meta_description"):
            val = metadata.get(key)
            if val and str(val).strip():
                excerpt = str(val).strip()[:300]
                break

    slug = None
    if metadata and metadata.get("slug"):
        slug = slugify_for_wordpress(str(metadata["slug"]))

    return WordPressDraftPayload(
        title=title[:300],
        content_html=content_html,
        excerpt=excerpt,
        slug=slug,
    )


async def create_draft_post(
    creds: ResolvedWordPressCredentials,
    payload: WordPressDraftPayload,
    *,
    client: httpx.AsyncClient | None = None,
    timeout_s: float = 45.0,
) -> WordPressCreateDraftResult:
    """POST wp/v2/posts with status=draft only."""
    url = f"{creds.site_base}/wp-json/wp/v2/posts"
    body: dict[str, Any] = {
        "title": payload.title,
        "content": payload.content_html,
        "status": "draft",
    }
    if payload.excerpt:
        body["excerpt"] = payload.excerpt
    if payload.slug:
        body["slug"] = payload.slug

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_s)

    try:
        resp = await client.post(
            url,
            json=body,
            auth=(creds.username, creds.application_password),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
    finally:
        if own_client:
            await client.aclose()

    summary: dict[str, Any] = {"method": "POST", "path": "/wp-json/wp/v2/posts", "url_host": urlparse(creds.site_base).netloc}

    if resp.status_code in (200, 201):
        try:
            data = resp.json()
        except json.JSONDecodeError:
            log.warning("wordpress.draft.invalid_json", http_status=resp.status_code)
            return WordPressCreateDraftResult(
                ok=False,
                http_status=resp.status_code,
                error="WordPress returned non-JSON success body.",
                response_summary={**summary, "parse_error": True},
            )
        pid = data.get("id")
        link = data.get("link")
        log.info(
            "wordpress.draft.created",
            http_status=resp.status_code,
            post_id=pid,
            link_host=urlparse(link).netloc if link else None,
        )
        return WordPressCreateDraftResult(
            ok=True,
            http_status=resp.status_code,
            wordpress_post_id=int(pid) if pid is not None else None,
            wordpress_post_url=str(link) if link else None,
            response_summary={**summary, "post_id": pid},
        )

    err_msg = f"HTTP {resp.status_code}"
    try:
        data = resp.json()
        if isinstance(data, dict) and data.get("message"):
            err_msg = f"{err_msg}: {data.get('message')}"
        if isinstance(data, dict) and data.get("code"):
            summary["wp_code"] = data.get("code")
    except json.JSONDecodeError:
        text_head = (resp.text or "")[:240].replace("\n", " ")
        if text_head:
            err_msg = f"{err_msg} — {text_head}"
    log.warning(
        "wordpress.draft.failed",
        http_status=resp.status_code,
        message_excerpt=err_msg[:200],
    )
    return WordPressCreateDraftResult(
        ok=False,
        http_status=resp.status_code,
        error=err_msg[:2000],
        response_summary=summary,
    )

