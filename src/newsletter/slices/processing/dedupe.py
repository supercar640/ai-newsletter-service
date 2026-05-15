"""Cluster items that point at the same article.

Two passes:

1. **Canonical URL exact match** — strong signal, group immediately.
2. **Title similarity within 24h** — catches the same story published
   to slightly different URLs (mobile vs desktop, syndicated copies).

A *group id* is just the canonical URL of the cluster's first member.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher

_TITLE_SIM_THRESHOLD = 0.88
_TIME_WINDOW = timedelta(hours=24)
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s가-힣ぁ-んァ-ン一-龯]+", flags=re.UNICODE)


@dataclass(slots=True)
class DedupeInput:
    """Per-item minimum needed to make a clustering decision."""

    key: int  # caller-supplied stable id (e.g. raw_item.id)
    canonical_url: str
    title: str
    published_at: datetime | None


def _title_signature(title: str) -> str:
    """Lowercase + strip punctuation + collapse whitespace."""
    cleaned = _PUNCT_RE.sub(" ", title.lower())
    return _WS_RE.sub(" ", cleaned).strip()


def _short_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def assign_groups(items: Iterable[DedupeInput]) -> dict[int, str]:
    """Return ``{item.key: duplicate_group_id}`` for every input item.

    Singletons get their own group (i.e. every item gets some id), so
    callers can store ``duplicate_group_id`` unconditionally.
    """
    items_list = list(items)
    by_key: dict[int, str] = {}

    # Pass 1: group by canonical URL exact match.
    url_groups: dict[str, str] = {}
    for item in items_list:
        if not item.canonical_url:
            continue
        gid = url_groups.setdefault(item.canonical_url, _short_id(item.canonical_url))
        by_key[item.key] = gid

    # Pass 2: title similarity for items still ungrouped (or merge into
    # an existing group when a strong match exists).
    representatives: list[tuple[str, DedupeInput]] = []
    for url, gid in url_groups.items():
        rep = next(it for it in items_list if it.canonical_url == url)
        representatives.append((gid, rep))

    for item in items_list:
        if item.key in by_key:
            continue
        sig = _title_signature(item.title)
        matched_gid: str | None = None
        for gid, rep in representatives:
            if _is_similar(sig, rep, item):
                matched_gid = gid
                break
        if matched_gid is None:
            matched_gid = _short_id(f"title:{sig}:{item.key}")
            representatives.append((matched_gid, item))
        by_key[item.key] = matched_gid

    return by_key


def _is_similar(sig: str, rep: DedupeInput, candidate: DedupeInput) -> bool:
    if not sig or not rep.title:
        return False
    if (
        rep.published_at is not None
        and candidate.published_at is not None
        and abs(rep.published_at - candidate.published_at) > _TIME_WINDOW
    ):
        return False
    ratio = SequenceMatcher(None, sig, _title_signature(rep.title)).ratio()
    return ratio >= _TITLE_SIM_THRESHOLD
