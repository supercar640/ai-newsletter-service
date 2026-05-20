"""Practical-track newsletter section (spec §8.2, Track B).

Mirrors :mod:`expert` structurally: per-cluster summarize (sonnet) →
section write (opus), with a deterministic local-template fallback when
the writer LLM fails. Reuses :class:`ClusterBrief` / :class:`ClusterMember`
from the expert module — the cluster data shape is identical; only the
editorial schema differs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from newsletter.core.llm import LLMClient, LLMError
from newsletter.core.logging import get_logger
from newsletter.core.prompts import load_prompt
from newsletter.slices.newsletter.expert import ClusterBrief, ClusterMember

if TYPE_CHECKING:
    from newsletter.slices.newsletter.department_tips import DepartmentTipItem

log = get_logger(__name__)

_SUMMARIZER_PROMPT = "practical-insight/practical-usecase-summarizer.md"
_WRITER_PROMPT = "practical-insight/practical-insight-writer.md"

_EXPECTED_USECASE_FIELDS = (
    "title",
    "scenario",
    "method",
    "prompt_example",
    "caveats",
)


@dataclass(slots=True, frozen=True)
class PracticalUsecase:
    """LLM-produced single usage-tip for the B section."""

    cluster_id: str
    title: str
    scenario: str
    method: str
    prompt_example: str
    caveats: str
    sources: tuple[dict[str, str], ...]


@dataclass(slots=True, frozen=True)
class PracticalSection:
    """Final B-section markdown plus the per-cluster usecases that built it."""

    markdown: str
    usecases: list[PracticalUsecase]
    department_tips: list[DepartmentTipItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 1: per-cluster summarization (sonnet)
# ---------------------------------------------------------------------------


def summarize_practical_cluster(brief: ClusterBrief, *, llm: LLMClient) -> PracticalUsecase | None:
    prompt = load_prompt(_SUMMARIZER_PROMPT)
    body = prompt.render(
        cluster_id=brief.cluster_id,
        members_block=_format_members(brief.members),
    )
    try:
        payload, _ = llm.complete_json(body, model=prompt.model, max_tokens=1024)
    except LLMError as exc:
        log.warning("practical.summarize.failed", cluster_id=brief.cluster_id, error=str(exc))
        return None

    if not isinstance(payload, dict):
        log.warning(
            "practical.summarize.bad_payload",
            cluster_id=brief.cluster_id,
            kind=type(payload).__name__,
        )
        return None

    missing = [k for k in _EXPECTED_USECASE_FIELDS if not payload.get(k)]
    if missing:
        log.warning(
            "practical.summarize.missing_fields",
            cluster_id=brief.cluster_id,
            missing=missing,
        )
        return None

    sources = _normalize_sources(payload.get("sources"), brief.members)
    return PracticalUsecase(
        cluster_id=brief.cluster_id,
        title=str(payload["title"]).strip(),
        scenario=str(payload["scenario"]).strip(),
        method=str(payload["method"]).strip(),
        prompt_example=str(payload["prompt_example"]).strip(),
        caveats=str(payload["caveats"]).strip(),
        sources=sources,
    )


def summarize_practical_clusters(
    briefs: list[ClusterBrief], *, llm: LLMClient
) -> list[PracticalUsecase]:
    out: list[PracticalUsecase] = []
    for brief in briefs:
        usecase = summarize_practical_cluster(brief, llm=llm)
        if usecase is not None:
            out.append(usecase)
    return out


# ---------------------------------------------------------------------------
# Stage 2: section writing (opus) + fallback
# ---------------------------------------------------------------------------


def write_practical_section(
    usecases: list[PracticalUsecase],
    *,
    date: str,
    llm: LLMClient,
) -> PracticalSection:
    if not usecases:
        return PracticalSection(markdown=_empty_section(date), usecases=[])

    prompt = load_prompt(_WRITER_PROMPT)
    body = prompt.render(
        date=date,
        usecases_json=json.dumps([_usecase_to_dict(u) for u in usecases], ensure_ascii=False),
    )
    try:
        response = llm.complete(body, model=prompt.model, max_tokens=4096)
    except LLMError as exc:
        log.warning("practical.writer.failed", error=str(exc))
        return PracticalSection(
            markdown=_local_render(usecases, date=date),
            usecases=usecases,
        )

    return PracticalSection(markdown=response.text.strip(), usecases=usecases)


def build_practical_section(
    briefs: list[ClusterBrief],
    *,
    date: str,
    llm: LLMClient,
) -> PracticalSection:
    """End-to-end: briefs → usecases → section markdown."""
    if not briefs:
        return PracticalSection(markdown=_empty_section(date), usecases=[])
    usecases = summarize_practical_clusters(briefs, llm=llm)
    return write_practical_section(usecases, date=date, llm=llm)


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
    """Coerce LLM ``sources`` into the contract downstream renderers expect."""
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

    for m in members:
        if m.url not in seen:
            out.append({"title": m.title, "url": m.url, "name": m.source_name})
            seen.add(m.url)

    return tuple(out)


def _usecase_to_dict(u: PracticalUsecase) -> dict[str, object]:
    return {
        "cluster_id": u.cluster_id,
        "title": u.title,
        "scenario": u.scenario,
        "method": u.method,
        "prompt_example": u.prompt_example,
        "caveats": u.caveats,
        "sources": list(u.sources),
    }


def _empty_section(date: str) -> str:
    return (
        "## B. 일반 임직원용 AI 활용 인사이트\n\n"
        f"_발행일: {date}_\n\n"
        "### 1. 이번 주 바로 써볼 AI 활용법\n"
        "- 이번 주 해당 내용 없음\n\n"
        "### 2. 부서별 활용 팁\n"
        "- 이번 주 해당 내용 없음\n\n"
        "### 3. 이번 주 추천 프롬프트\n"
        "- 이번 주 해당 내용 없음\n\n"
        "### 4. AI 사용 시 주의할 점\n"
        "- 이번 주 해당 내용 없음\n"
    )


def _local_render(usecases: list[PracticalUsecase], *, date: str) -> str:
    """Deterministic markdown fallback when the writer LLM fails."""
    lines: list[str] = [
        "## B. 일반 임직원용 AI 활용 인사이트",
        "",
        f"_발행일: {date}_",
        "",
        "### 1. 이번 주 바로 써볼 AI 활용법",
        "",
    ]
    for idx, u in enumerate(usecases, 1):
        lines.append(f"#### 활용법 {idx}. {u.title}")
        lines.append(f"- 이런 상황에 사용: {u.scenario}")
        lines.append(f"- 사용 방법: {u.method}")
        lines.append(f"- 예시 프롬프트: {u.prompt_example}")
        lines.append(f"- 주의사항: {u.caveats}")
        lines.append("")

    lines.extend(
        [
            "### 2. 부서별 활용 팁",
            "- (작성기 폴백 모드 — 별도 분류 없음)",
            "",
            "### 3. 이번 주 추천 프롬프트",
        ]
    )
    for u in usecases[:3]:
        lines.append(f"- {u.prompt_example}")
    if not usecases:
        lines.append("- (작성기 폴백 모드 — 별도 추천 없음)")
    lines.extend(
        [
            "",
            "### 4. AI 사용 시 주의할 점",
        ]
    )
    seen_caveats: set[str] = set()
    for u in usecases:
        if u.caveats and u.caveats not in seen_caveats:
            lines.append(f"- {u.caveats}")
            seen_caveats.add(u.caveats)
    if not seen_caveats:
        lines.append("- (작성기 폴백 모드 — 별도 분류 없음)")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "PracticalSection",
    "PracticalUsecase",
    "build_practical_section",
    "summarize_practical_cluster",
    "summarize_practical_clusters",
    "write_practical_section",
]
