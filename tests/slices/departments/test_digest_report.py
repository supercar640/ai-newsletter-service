"""departments.report — deterministic markdown rendering of a digest."""

from __future__ import annotations

from datetime import date

from newsletter.slices.departments.report import render_markdown
from newsletter.slices.departments.schemas import (
    DepartmentDigest,
    DepartmentDigestEntry,
    RelevantHeadline,
)


def _digest(*, mode="keyword", departments=()) -> DepartmentDigest:
    return DepartmentDigest(
        since=date(2026, 5, 15),
        until=date(2026, 5, 22),
        total_items=12,
        mode=mode,
        departments=list(departments),
    )


def test_header_period_and_mode():
    md = render_markdown(_digest(mode="embedding"))
    assert "# 부서별 다이제스트" in md
    assert "2026-05-15" in md and "2026-05-22" in md
    assert "12" in md
    assert "임베딩" in md


def test_no_departments_marker():
    md = render_markdown(_digest(departments=[]))
    assert "(등록된 부서 없음)" in md


def test_department_sections_and_empty():
    entries = [
        DepartmentDigestEntry(
            name="영업",
            headlines=[RelevantHeadline(title="고객 사례", url="https://e.com/a", score=2.0)],
        ),
        DepartmentDigestEntry(name="관리", headlines=[]),
    ]
    md = render_markdown(_digest(departments=entries))
    assert "## 영업" in md
    assert "[고객 사례](https://e.com/a)" in md
    assert "## 관리" in md
    assert "(관련 기사 없음)" in md
    assert "키워드" in md
