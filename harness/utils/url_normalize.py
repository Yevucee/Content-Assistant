"""URL canonicalisation for deduplication."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def normalize_url(url: str) -> str:
    """
    Stable key for deduping: lower host, drop fragment, trim trailing path slash,
    sort query params (optional light normalisation).
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.netloc and parsed.path.startswith("//"):
        parsed = urlparse(f"https:{raw}")
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path or ""
    path = path.rstrip("/") if path != "/" else path
    if not path:
        path = "/"
    q = parse_qsl(parsed.query, keep_blank_values=True)
    q_sorted = urlencode(sorted(q))
    return urlunparse((scheme, netloc, path, "", q_sorted, ""))
