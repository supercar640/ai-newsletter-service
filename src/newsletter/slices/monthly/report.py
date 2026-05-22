"""Deterministic markdown rendering of a MonthlyReport."""

from __future__ import annotations

from newsletter.slices.monthly.schemas import MonthlyReport

_NARRATIVE_FALLBACK = "(요약 생략 — LLM 비활성)"


def render_markdown(report: MonthlyReport) -> str:
    lines: list[str] = [
        f"# {report.month} AI 동향 리포트",
        "",
        f"- 기간: {report.since} ~ {report.until} (exclusive)",
        f"- 스캔한 기사: {report.total_items}건",
        "",
        "## 이번 달 요약",
        report.narrative if report.narrative else _NARRATIVE_FALLBACK,
        "",
        "## 트렌드",
        *_trend_lines(report),
        "",
        "## 경쟁사 동향",
        *_competitor_lines(report),
        "",
        "## 주요 기사",
        *_headline_lines(report),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _trend_lines(report: MonthlyReport) -> list[str]:
    t = report.trend
    rising = ", ".join(d.term for d in t.rising[:10])
    new = ", ".join(d.term for d in t.new[:10])
    top = ", ".join(d.term for d in t.top_current[:10])
    if not (rising or new or top):
        return ["(데이터 없음)"]
    out: list[str] = []
    if rising:
        out.append(f"- 떠오르는: {rising}")
    if new:
        out.append(f"- 신규: {new}")
    if top:
        out.append(f"- 상위: {top}")
    return out


def _competitor_lines(report: MonthlyReport) -> list[str]:
    mentions = report.competitors.competitors
    if not mentions:
        return ["(경쟁사 미등록)"]
    return [f"- {m.name}: {m.count}건" for m in mentions]


def _headline_lines(report: MonthlyReport) -> list[str]:
    if not report.top_headlines:
        return ["(기사 없음)"]
    return [f"- [{h.title}]({h.url})" for h in report.top_headlines]


__all__ = ["render_markdown"]
