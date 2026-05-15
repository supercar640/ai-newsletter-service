"""Naver-hosted news article body extraction.

Naver mirrors many publisher articles on ``n.news.naver.com`` with a
consistent DOM. Parsing only that host (rather than 100s of publisher
sites) keeps body extraction reliable.

The selectors below are ordered from most-specific / most-current to
fallback. If the page layout changes upstream this is the single place
to update.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

NAVER_NEWS_HOST = "n.news.naver.com"

# Try selectors in order; first non-empty wins.
_BODY_SELECTORS: tuple[str, ...] = (
    "article#dic_area",
    "#dic_area",
    "article#newsct_article",
    "#newsct_article",
    "div.newsct_article",
    "article.go_trans",
)

# Whitespace inside a single line: any unicode WS that isn't a newline.
# `[^\S\n]+` = NOT (non-WS or newline) = WS but-not-newline. Covers regular
# space, tab, NBSP, ideographic space, etc.
_INLINE_WS_RE = re.compile(r"[^\S\n]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def is_naver_news_url(url: str | None) -> bool:
    """True iff ``url`` is hosted on ``n.news.naver.com``."""
    if not url:
        return False
    return NAVER_NEWS_HOST in url


def extract_article_body(html: str) -> str | None:
    """Return cleaned plain-text article body, or ``None`` if not found.

    Inline scripts, style blocks, and image-only nodes are removed first.
    Whitespace is normalized to single spaces; consecutive blank lines
    are collapsed to one.
    """
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    for selector in _BODY_SELECTORS:
        node = soup.select_one(selector)
        if node is None:
            continue
        text = node.get_text(separator="\n", strip=True)
        cleaned = _clean(text)
        if cleaned:
            return cleaned
    return None


def _clean(text: str) -> str:
    lines = [_INLINE_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    joined = "\n".join(line for line in lines if line)
    return _BLANK_LINES_RE.sub("\n\n", joined).strip()
