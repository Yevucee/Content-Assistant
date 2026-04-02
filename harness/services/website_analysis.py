"""Limited-scope website / blog sampling and style inference (no broad crawling)."""

from __future__ import annotations

import os
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import structlog

from harness.schemas.brand_template import BrandTemplateProfile
from harness.schemas.inputs import WebsiteDiscoveryInput
from harness.schemas.website_analysis import (
    ContentOpportunitySuggestion,
    FetchedPageDigest,
    WebsiteAnalysisPackage,
)
from harness.services import llm as llm_svc
from harness.services.prompts_env import get_prompt_env
from harness.utils.url_normalize import normalize_url

log = structlog.get_logger(__name__)

DEFAULT_UA = "ContentHarness/0.3 (+https://example.local; editorial site sampler)"
FETCH_TIMEOUT = float(os.environ.get("WEBSITE_FETCH_TIMEOUT", "15"))
MAX_HTML_BYTES = int(os.environ.get("WEBSITE_MAX_HTML_BYTES", "400000"))
MAX_BLOG_SEEDS = 8
MAX_TOTAL_PAGES = int(os.environ.get("WEBSITE_MAX_TOTAL_PAGES", "8"))
MAX_EXCERPT_WORDS = 450
_INTERNAL_PATH_HINT = re.compile(
    r"(/blog|/news|/articles?|/posts?|/stories|/insights|/journal|/updates|/resources)(/|$)",
    re.I,
)


def _http_client() -> httpx.Client:
    return httpx.Client(
        timeout=FETCH_TIMEOUT,
        headers={"User-Agent": os.environ.get("SOURCE_USER_AGENT", DEFAULT_UA)},
        follow_redirects=True,
)


def _strip_html_to_text(html: str, max_chars: int) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", html)
    t = unescape(re.sub(r"\s+", " ", t)).strip()
    return t[:max_chars]


def _heading_outline(html: str, limit: int = 14) -> str:
    heads: list[str] = []
    for m in re.finditer(r"<h([1-3])[^>]*>([\s\S]*?)</h\1>", html, re.I):
        raw = re.sub(r"<[^>]+>", " ", m.group(2))
        line = unescape(re.sub(r"\s+", " ", raw)).strip()
        if len(line) > 2:
            heads.append(line[:200])
        if len(heads) >= limit:
            break
    return " | ".join(heads)


def _extract_title_desc(html: str) -> tuple[str, str]:
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
    return title[:500], desc[:2000]


def _same_host(a: str, b: str) -> bool:
    return (urlparse(a).netloc or "").lower() == (urlparse(b).netloc or "").lower()


def _discover_internal_links(home_url: str, html: str, limit: int) -> list[str]:
    if limit <= 0:
        return []
    base = home_url
    seen: set[str] = set()
    out: list[str] = []
    for m in re.finditer(r'''href\s*=\s*['"]([^'"]+)['"]''', html, re.I):
        href = (m.group(1) or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        abs_u = urljoin(base, href)
        nu = normalize_url(abs_u)
        if not nu or nu in seen or not _same_host(nu, home_url):
            continue
        path = urlparse(nu).path or "/"
        if not _INTERNAL_PATH_HINT.search(path):
            continue
        seen.add(nu)
        out.append(nu)
        if len(out) >= limit:
            break
    return out


def _fetch_html(url: str, client: httpx.Client) -> tuple[str | None, str | None]:
    try:
        r = client.get(url)
        r.raise_for_status()
        raw = r.text
        if len(raw.encode("utf-8", errors="ignore")) > MAX_HTML_BYTES:
            raw = raw[:MAX_HTML_BYTES]
        final = str(r.url)
        return raw, final
    except Exception as e:  # noqa: BLE001
        log.warning("website.fetch_failed", url=url, error=str(e))
        return None, None


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text) if w])


def _build_fetch_queue(inp: WebsiteDiscoveryInput) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """Returns list of (url, discovered_via) and scope metadata."""
    home = normalize_url((inp.website_url or "").strip())
    if not home:
        return [], {"error": "no_website_url"}

    seeds: list[tuple[str, str]] = [(home, "homepage")]
    seen: set[str] = {home}

    for u in (inp.blog_urls or [])[:MAX_BLOG_SEEDS]:
        nu = normalize_url(u.strip())
        if nu and nu not in seen:
            seen.add(nu)
            seeds.append((nu, "blog_url"))

    scope = {
        "homepage": home,
        "explicit_blog_urls": len([s for s in seeds if s[1] == "blog_url"]),
        "max_internal_links_requested": inp.max_internal_links,
        "caps": {"max_total_pages": MAX_TOTAL_PAGES, "max_html_bytes": MAX_HTML_BYTES},
    }
    return seeds, scope


def collect_page_digests(inp: WebsiteDiscoveryInput) -> tuple[list[FetchedPageDigest], dict[str, Any]]:
    """Fetch homepage (+ blog seeds), then a limited set of same-site blog-like links."""
    seeds, scope = _build_fetch_queue(inp)
    queue: list[tuple[str, str]] = list(seeds)
    queued_urls: set[str] = {normalize_url(u) for u, _ in queue if normalize_url(u)}
    digests: list[FetchedPageDigest] = []
    internal_budget = max(0, min(inp.max_internal_links, 8))

    with _http_client() as client:
        pos = 0
        while pos < len(queue) and len(digests) < MAX_TOTAL_PAGES:
            url, via = queue[pos]
            pos += 1
            html, final = _fetch_html(url, client)
            if not html or not final:
                continue
            title, desc = _extract_title_desc(html)
            body_text = _strip_html_to_text(html, 25_000)
            excerpt_words = body_text.split()[:MAX_EXCERPT_WORDS]
            excerpt = " ".join(excerpt_words)
            if desc and len(excerpt) < 80:
                excerpt = f"{desc}\n\n{excerpt}".strip()
            heads = _heading_outline(html)
            digests.append(
                FetchedPageDigest(
                    url=final,
                    title=title or url,
                    discovered_via=via,
                    summary_excerpt=excerpt[:6000],
                    heading_outline=heads[:3000],
                    word_count_approx=_word_count(body_text),
                ),
            )
            if via == "homepage" and internal_budget > 0:
                discovered = _discover_internal_links(final, html, internal_budget)
                for u in discovered:
                    nu = normalize_url(u)
                    if (
                        nu
                        and nu not in queued_urls
                        and len(digests) + (len(queue) - pos) < MAX_TOTAL_PAGES + 15
                    ):
                        queued_urls.add(nu)
                        queue.append((nu, "internal_link"))
                internal_budget = 0

    scope["pages_fetched"] = len(digests)
    scope["attempted_urls"] = [d.url for d in digests]
    return digests, scope


def _skip_llm() -> bool:
    return os.environ.get("SKIP_WEBSITE_LLM", "").lower() in ("1", "true", "yes")


def _heuristic_template(
    digests: list[FetchedPageDigest],
    brand_name: str | None,
) -> tuple[BrandTemplateProfile, list[ContentOpportunitySuggestion], list[str]]:
    notes = ["Heuristic template (LLM skipped or unavailable); treat as first pass."]
    corpus = " ".join(d.summary_excerpt for d in digests)[:12000].lower()
    tone = "Professional web presence"
    if any(w in corpus for w in ("charity", "donate", "nonprofit", "community")):
        tone = "Community-oriented, mission-driven"
    elif any(w in corpus for w in ("innovation", "scale", "enterprise")):
        tone = "Business-focused, forward-looking"

    headings = " | ".join(d.heading_outline[:500] for d in digests if d.heading_outline)
    tmpl = BrandTemplateProfile(
        tone_summary=tone,
        audience="Site visitors and readers implied by on-page copy (confirm manually).",
        intro_style="Use clear topical openings consistent with sampled pages." if digests else "",
        heading_style=f"Observed headings include: {headings[:800]}" if headings else "",
        narrative_style="Mixed / not enough sample to pin down" if len(digests) < 2 else "Review sample articles for list vs narrative balance.",
        cta_style="Look for newsletter, contact, or donate patterns in full site review.",
        category_hints=["Editorial derived from site themes"],
    )
    opps: list[ContentOpportunitySuggestion] = []
    for d in digests[:4]:
        if d.discovered_via != "blog_url" and d.discovered_via != "internal_link":
            continue
        opp_title = d.title or "Follow-on article in site’s editorial lane"
        opps.append(
            ContentOpportunitySuggestion(
                working_title=f"Deeper dive: {opp_title[:80]}",
                angle="Extend themes visible in this sampled URL for the same audience.",
                rationale=f"Grounded in fetched page {d.url}",
                suggested_category=None,
            ),
        )
    if not opps and digests:
        opps.append(
            ContentOpportunitySuggestion(
                working_title="Site-aligned explainer or story",
                angle="Mirror the tone and structure of the homepage sample.",
                rationale="Limited blog URLs; opportunity is generic.",
            ),
        )
    return tmpl, opps, notes


def _coerce_template(data: dict[str, Any]) -> BrandTemplateProfile:
    raw = data.get("proposed_template") or data.get("template") or {}
    if not isinstance(raw, dict):
        raw = {}
    try:
        return BrandTemplateProfile.model_validate(raw)
    except Exception:  # noqa: BLE001
        return BrandTemplateProfile()


def _coerce_opportunities(raw: Any) -> list[ContentOpportunitySuggestion]:
    if not isinstance(raw, list):
        return []
    out: list[ContentOpportunitySuggestion] = []
    for row in raw[:12]:
        if not isinstance(row, dict):
            continue
        title = str(row.get("working_title") or "").strip()
        if not title:
            continue
        out.append(
            ContentOpportunitySuggestion(
                working_title=title[:500],
                angle=str(row.get("angle") or "")[:2000],
                rationale=str(row.get("rationale") or "")[:2000],
                suggested_category=(str(row.get("suggested_category")).strip()[:200] or None)
                if row.get("suggested_category")
                else None,
            ),
        )
    return out


def _llm_analyse(
    inp: WebsiteDiscoveryInput,
    digests: list[FetchedPageDigest],
) -> tuple[BrandTemplateProfile, list[ContentOpportunitySuggestion], list[str]] | None:
    if _skip_llm() or not digests:
        return None
    env = get_prompt_env()
    tmpl = env.get_template("website_style_analysis.j2")
    user = tmpl.render(
        brand_name=(inp.brand_name or "").strip(),
        extra_notes=(inp.extra_notes or "").strip(),
        pages=[d.model_dump() for d in digests],
    )
    system = "You output only JSON per the schema in the user message. No markdown fences."
    try:
        data = llm_svc.chat_json(system=system, user=user, temperature=0.35)
        if not isinstance(data, dict):
            return None
        prof = _coerce_template(data)
        opps = _coerce_opportunities(data.get("content_opportunities"))
        notes_raw = data.get("analysis_notes")
        notes: list[str] = []
        if isinstance(notes_raw, list):
            notes = [str(x).strip() for x in notes_raw if str(x).strip()][:20]
        log.info("website.llm_ok", opportunities=len(opps))
        return prof, opps, notes
    except Exception as e:  # noqa: BLE001
        log.warning("website.llm_failed", error=str(e))
        return None


def run_website_discovery_analysis(inp: WebsiteDiscoveryInput) -> WebsiteAnalysisPackage:
    """
    Fetch a capped set of pages and produce a suggested BrandTemplateProfile + opportunities.

    Does not write brand YAML — suggestions only.
    """
    digests, scope = collect_page_digests(inp)
    brand_ctx = (inp.brand_name or "").strip() or urlparse(
        (inp.website_url or "").strip() or "http://local",
    ).netloc

    llm_result = _llm_analyse(inp, digests)
    if llm_result:
        tmpl, opps, notes = llm_result
        notes = list(notes) + [f"Sampled {len(digests)} page(s) within configured caps."]
    else:
        tmpl, opps, notes = _heuristic_template(digests, inp.brand_name)

    if not digests:
        notes.append("No pages fetched — check website_url and network access.")

    return WebsiteAnalysisPackage(
        target_site=normalize_url((inp.website_url or "").strip()) or "",
        brand_name_context=brand_ctx[:500],
        fetch_scope=scope,
        pages=digests,
        proposed_brand_template=tmpl,
        content_opportunities=opps,
        analysis_notes=notes,
    )
