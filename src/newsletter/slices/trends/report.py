"""Deterministic markdown rendering of a TrendReport."""

from __future__ import annotations

from newsletter.slices.trends.schemas import TermDelta, TrendReport

_SECTIONS = (
    ("🔼 떠오르는", "rising"),
    ("🆕 신규", "new"),
    ("🔽 식는", "fading"),
    ("⬇️ 소멸", "dropped"),
    ("📊 현재 상위", "top_current"),
)


def render_markdown(report: TrendReport) -> str:
    w = report.window
    lines: list[str] = [
        f"# 트렌드 리포트 — {w.period}",
        "",
        f"- 현재 기간: {w.current_start} ~ {w.current_end} (exclusive), "
        f"기사 {report.total_current_items}건",
        f"- 직전 기간: {w.previous_start} ~ {w.previous_end} (exclusive), "
        f"기사 {report.total_previous_items}건",
        "",
    ]
    for heading, attr in _SECTIONS:
        lines.append(f"## {heading}")
        rows: list[TermDelta] = getattr(report, attr)
        if not rows:
            lines.append("(없음)")
            lines.append("")
            continue
        lines.append("| 용어 | 현재 | 직전 | Δ |")
        lines.append("|---|---:|---:|---:|")
        for d in rows:
            lines.append(f"| {d.term} | {d.current} | {d.previous} | {d.delta:+d} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_markdown"]
