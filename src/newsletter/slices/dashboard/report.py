"""Deterministic markdown rendering of a DashboardReport."""

from __future__ import annotations

from newsletter.slices.dashboard.schemas import DashboardReport


def render_markdown(report: DashboardReport) -> str:
    lines: list[str] = [
        "# 성과 대시보드",
        "",
        f"- 기간: {report.since} ~ {report.until} (exclusive)",
        "",
        "## 소스별 성과",
        *_source_lines(report),
        "",
        "## 품질 요약",
        *_quality_lines(report),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _source_lines(report: DashboardReport) -> list[str]:
    if not report.sources:
        return ["(데이터 없음)"]
    out = [
        "| 소스 | 트랙 | 수집 | 처리 | 평균 relevance | 평균 importance |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for s in report.sources:
        out.append(
            f"| {s.name} | {s.content_track} | {s.collected} | {s.processed} | "
            f"{s.avg_relevance:.2f} | {s.avg_importance:.2f} |"
        )
    return out


def _quality_lines(report: DashboardReport) -> list[str]:
    q = report.quality
    out = [f"- 전체 수집: {q.total_collected}건 / 처리: {q.total_processed}건"]
    if q.track_counts:
        tracks = ", ".join(f"{k}: {v}" for k, v in sorted(q.track_counts.items()))
        out.append(f"- 트랙: {tracks}")
    else:
        out.append("- 트랙: (없음)")
    out.append(
        f"- 중복: 처리 {q.total_processed}건 중 그룹화 {q.grouped_items}건 "
        f"/ 고유 그룹 {q.distinct_groups}개"
    )
    out.append("")
    out.append("### 상위 카테고리")
    if not q.top_categories:
        out.append("(없음)")
    else:
        out.append("| 카테고리 | 건수 |")
        out.append("|---|---:|")
        for cat, count in q.top_categories:
            out.append(f"| {cat} | {count} |")
    return out


__all__ = ["render_markdown"]
