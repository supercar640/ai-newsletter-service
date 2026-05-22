"""Deterministic markdown rendering of a CompetitorReport."""

from __future__ import annotations

from newsletter.slices.competitors.schemas import CompetitorReport


def render_markdown(report: CompetitorReport) -> str:
    lines: list[str] = [
        "# 경쟁사 멘션 리포트",
        "",
        f"- 기간: {report.since} ~ {report.until} (exclusive)",
        f"- 스캔한 기사: {report.total_items}건",
        "",
    ]
    for m in report.competitors:
        lines.append(f"## {m.name} — {m.count}건")
        if not m.headlines:
            lines.append("(언급 없음)")
            lines.append("")
            continue
        for h in m.headlines:
            lines.append(f"- [{h.title}]({h.url})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_markdown"]
