"""Deterministic markdown rendering of a DepartmentDigest."""

from __future__ import annotations

from newsletter.slices.departments.schemas import DepartmentDigest


def render_markdown(digest: DepartmentDigest) -> str:
    mode_label = "임베딩" if digest.mode == "embedding" else "키워드"
    lines: list[str] = [
        "# 부서별 다이제스트",
        "",
        f"- 기간: {digest.since} ~ {digest.until} (exclusive)",
        f"- 스캔한 기사: {digest.total_items}건",
        f"- 관련도: {mode_label}",
        "",
    ]
    if not digest.departments:
        lines.append("(등록된 부서 없음)")
        return "\n".join(lines).rstrip() + "\n"
    for d in digest.departments:
        lines.append(f"## {d.name}")
        if not d.headlines:
            lines.append("(관련 기사 없음)")
        else:
            lines.extend(f"- [{h.title}]({h.url})" for h in d.headlines)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_markdown"]
