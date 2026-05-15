"""Title + URL normalization."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "utm_id",
        "fbclid",
        "gclid",
        "yclid",
        "mc_cid",
        "mc_eid",
        "_ga",
        "ref",
        "ref_src",
    }
)

_WS_RE = re.compile(r"\s+")


def normalize_title(title: str | None) -> str:
    """Trim, collapse whitespace, strip stray quotes."""
    if not title:
        return ""
    cleaned = _WS_RE.sub(" ", title).strip()
    # Strip outermost matched quotes if the entire title is wrapped.
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'", "“", "”"}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def canonical_url(url: str | None) -> str:
    """Strip tracking params and lowercase scheme/host. Path/query preserved."""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    # Drop www. prefix for canonical comparison
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path or "/"
    # Strip default trailing slash on bare hostnames so a/b matches a/b/
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(query_pairs, doseq=True)
    # Drop fragment — never useful for identity.
    return urlunparse((scheme, netloc, path, parsed.params, query, ""))
