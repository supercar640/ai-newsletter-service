"""Expert-track newsletter section (spec §8.2, Track A).

Two-stage pipeline:

1. Per-cluster summarization (:func:`summarize_cluster`) — sonnet pulls
   each cluster's items into a single ``{title, summary, why_it_matters,
   company_perspective, sources}`` JSON block.
2. Section writing (:func:`write_expert_section`) — opus arranges the
   cluster summaries into the spec'd Korean markdown layout.

When the writer fails (LLM error, network), we fall back to a local
template render so the rest of the pipeline keeps moving. Empty input
(no candidate clusters) short-circuits and never spends an LLM call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from newsletter.core.llm import LLMClient, LLMError
from newsletter.core.logging import get_logger
from newsletter.core.prompts import load_prompt

log = get_logger(__name__)

_SUMMARIZER_PROMPT = "expert-news/expert-cluster-summarizer.md"
_WRITER_PROMPT = "expert-news/expert-news-writer.md"

_EXPECTED_SUMMARY_FIELDS = (
    "title",
    "summary",
    "why_it_matters",
    "company_perspective",
)


@dataclass(slots=True, frozen=True)
class ClusterMember:
    """One ProcessedItem resolved into the fields the summarizer needs."""

    id: int
    title: str
    url: str
    summary: str | None
    source_name: str


@dataclass(slots=True, frozen=True)
class ClusterBrief:
    """A cluster ready for summarization — members already resolved."""

    cluster_id: str
    score: float
    members: tuple[ClusterMember, ...]


@dataclass(slots=True, frozen=True)
class ClusterSummary:
    """LLM-produced editorial summary for one cluster."""

    cluster_id: str
    title: str
    summary: str
    why_it_matters: str
    company_perspective: str
    sources: tuple[dict[str, str], ...]


@dataclass(slots=True, frozen=True)
class ExpertSection:
    """Final A-section markdown plus the per-cluster summaries that built it."""

    markdown: str
    cluster_summaries: list[ClusterSummary]


# ---------------------------------------------------------------------------
# Stage 1: per-cluster summarization (sonnet)
# ---------------------------------------------------------------------------


def summarize_cluster(brief: ClusterBrief, *, llm: LLMClient) -> ClusterSummary | None:
    """Ask the cluster summarizer prompt for one cluster's JSON block."""
    prompt = load_prompt(_SUMMARIZER_PROMPT)
    body = prompt.render(
        cluster_id=brief.cluster_id,
        members_block=_format_members(brief.members),
    )
    try:
        payload, _ = llm.complete_json(body, tier=prompt.tier, max_tokens=1024)
    except LLMError as exc:
        log.warning("expert.summarize.failed", cluster_id=brief.cluster_id, error=str(exc))
        return None

    if not isinstance(payload, dict):
        log.warning(
            "expert.summarize.bad_payload",
            cluster_id=brief.cluster_id,
            kind=type(payload).__name__,
        )
        return None

    missing = [k for k in _EXPECTED_SUMMARY_FIELDS if not payload.get(k)]
    if missing:
        log.warning(
            "expert.summarize.missing_fields",
            cluster_id=brief.cluster_id,
            missing=missing,
        )
        return None

    sources = _normalize_sources(payload.get("sources"), brief.members)
    return ClusterSummary(
        cluster_id=brief.cluster_id,
        title=str(payload["title"]).strip(),
        summary=str(payload["summary"]).strip(),
        why_it_matters=str(payload["why_it_matters"]).strip(),
        company_perspective=str(payload["company_perspective"]).strip(),
        sources=sources,
    )


def summarize_clusters(
    briefs: list[ClusterBrief],
    *,
    llm: LLMClient,
) -> list[ClusterSummary]:
    """Summarize each brief, skipping ones whose LLM call failed."""
    out: list[ClusterSummary] = []
    for brief in briefs:
        summary = summarize_cluster(brief, llm=llm)
        if summary is not None:
            out.append(summary)
    return out


# ---------------------------------------------------------------------------
# Stage 2: section writing (opus) + fallback
# ---------------------------------------------------------------------------


def write_expert_section(
    summaries: list[ClusterSummary],
    *,
    date: str,
    llm: LLMClient,
) -> ExpertSection:
    """Render the A-section markdown from cluster summaries.

    Empty ``summaries`` short-circuits to a placeholder section. If the
    writer LLM call fails, we fall back to a local template render so
    downstream stages can still run.
    """
    if not summaries:
        return ExpertSection(markdown=_empty_section(date), cluster_summaries=[])

    prompt = load_prompt(_WRITER_PROMPT)
    body = prompt.render(
        date=date,
        cluster_summaries_json=json.dumps(
            [_summary_to_dict(s) for s in summaries], ensure_ascii=False
        ),
    )
    try:
        response = llm.complete(body, tier=prompt.tier, max_tokens=4096)
    except LLMError as exc:
        log.warning("expert.writer.failed", error=str(exc))
        return ExpertSection(
            markdown=_local_render(summaries, date=date),
            cluster_summaries=summaries,
        )

    return ExpertSection(markdown=response.text.strip(), cluster_summaries=summaries)


def build_expert_section(
    briefs: list[ClusterBrief],
    *,
    date: str,
    llm: LLMClient,
) -> ExpertSection:
    """End-to-end: briefs → summaries → section markdown."""
    if not briefs:
        return ExpertSection(markdown=_empty_section(date), cluster_summaries=[])
    summaries = summarize_clusters(briefs, llm=llm)
    return write_expert_section(summaries, date=date, llm=llm)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_members(members: tuple[ClusterMember, ...]) -> str:
    lines: list[str] = []
    for idx, m in enumerate(members, 1):
        lines.append(f"{idx}. [{m.source_name}] {m.title}")
        lines.append(f"   url: {m.url}")
        if m.summary:
            snippet = m.summary.strip().replace("\n", " ")
            if len(snippet) > 500:
                snippet = snippet[:500] + "…"
            lines.append(f"   summary: {snippet}")
    return "\n".join(lines)


def _normalize_sources(
    raw_sources: object,
    members: tuple[ClusterMember, ...],
) -> tuple[dict[str, str], ...]:
    """Coerce the LLM's ``sources`` array into the contract we ship downstream.

    The model may omit fields or invent URLs; we drop anything that's
    missing a URL and trust the original member URL as the canonical
    fallback when fields are sparse.
    """
    by_url = {m.url: m for m in members}
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    if isinstance(raw_sources, list):
        for item in raw_sources:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url or url in seen:
                continue
            member = by_url.get(url)
            out.append(
                {
                    "title": str(item.get("title") or (member.title if member else "")).strip(),
                    "url": url,
                    "name": str(item.get("name") or (member.source_name if member else "")).strip(),
                }
            )
            seen.add(url)

    # Ensure every member URL is represented at least once.
    for m in members:
        if m.url not in seen:
            out.append({"title": m.title, "url": m.url, "name": m.source_name})
            seen.add(m.url)

    return tuple(out)


def _summary_to_dict(s: ClusterSummary) -> dict[str, object]:
    return {
        "cluster_id": s.cluster_id,
        "title": s.title,
        "summary": s.summary,
        "why_it_matters": s.why_it_matters,
        "company_perspective": s.company_perspective,
        "sources": list(s.sources),
    }


def _empty_section(date: str) -> str:
    return (
        "## A. AI 전문가용 최신 AI 뉴스\n\n"
        f"_발행일: {date}_\n\n"
        "### 1. 이번 주 핵심 AI 동향 3줄 요약\n"
        "- 이번 주 해당 내용 없음\n\n"
        "### 2. 주요 뉴스\n"
        "- 이번 주 해당 내용 없음\n\n"
        "### 3. 주목할 기술·제품 업데이트\n"
        "- 이번 주 해당 내용 없음\n\n"
        "### 4. 정책·규제·시장 이슈\n"
        "- 이번 주 해당 내용 없음\n\n"
        "### 5. 더 읽어볼 링크\n"
        "- 이번 주 해당 내용 없음\n"
    )


def _local_render(summaries: list[ClusterSummary], *, date: str) -> str:
    """Deterministic markdown fallback when the writer LLM fails."""
    lines: list[str] = [
        "## A. AI 전문가용 최신 AI 뉴스",
        "",
        f"_발행일: {date}_",
        "",
        "### 1. 이번 주 핵심 AI 동향 3줄 요약",
    ]
    for s in summaries[:3]:
        lines.append(f"- {s.title}")
    if len(summaries) < 3:
        for _ in range(3 - len(summaries)):
            lines.append("- (자료 부족)")
    lines.append("")

    lines.append("### 2. 주요 뉴스")
    lines.append("")
    for idx, s in enumerate(summaries, 1):
        lines.append(f"#### 뉴스 {idx}. {s.title}")
        lines.append(f"- 요약: {s.summary}")
        lines.append(f"- 왜 중요한가: {s.why_it_matters}")
        lines.append(f"- 회사 관점: {s.company_perspective}")
        lines.append("- 원문:")
        for src in s.sources:
            url = src.get("url", "")
            name = src.get("name", "")
            title = src.get("title", "")
            lines.append(f"  - [{name} — {title}]({url})")
        lines.append("")

    lines.extend(
        [
            "### 3. 주목할 기술·제품 업데이트",
            "- (작성기 폴백 모드 — 별도 분류 없음)",
            "",
            "### 4. 정책·규제·시장 이슈",
            "- (작성기 폴백 모드 — 별도 분류 없음)",
            "",
            "### 5. 더 읽어볼 링크",
            "- (작성기 폴백 모드 — 별도 추천 없음)",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "ClusterBrief",
    "ClusterMember",
    "ClusterSummary",
    "ExpertSection",
    "build_expert_section",
    "summarize_cluster",
    "summarize_clusters",
    "write_expert_section",
]
