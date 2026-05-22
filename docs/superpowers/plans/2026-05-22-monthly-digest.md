# Monthly AI Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `monthly` slice that aggregates one calendar month of trends + competitor mentions + top importance-ranked headlines, adds an LLM narrative summary, and renders the result as markdown or HTML.

**Architecture:** A new vertical slice `monthly/{schemas,service,narrative,report,cli}.py`. `service` reuses `trends.analyze_trends` and `competitors.analyze_competitors` plus an importance-ranked top-headlines query (the importance score already reflects the company-interest boost). `narrative` feeds the deterministic digest to the writer LLM (opus) and returns prose, or `None` when the LLM is unavailable. `report` renders markdown; HTML is derived via the Stage-1 `core/report_html`.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Typer, `markdown-it-py`, Anthropic SDK (via `core/llm`), pytest.

---

## Design Source

Full design: `docs/superpowers/specs/2026-05-22-monthly-digest-design.md`. Brainstorming complete — do not re-brainstorm. Depends on Stage 1 (`core/report_html`, already merged).

## File Structure

| Kind | Path | Responsibility |
|---|---|---|
| Create | `src/newsletter/slices/monthly/__init__.py` | package marker |
| Create | `src/newsletter/slices/monthly/schemas.py` | `TopHeadline`, `MonthlyReport` dataclasses (reuse Trend/Competitor reports) |
| Create | `src/newsletter/slices/monthly/service.py` | DB: month-window aggregation → `MonthlyReport` (no narrative) |
| Create | `src/newsletter/slices/monthly/narrative.py` | LLM: digest → Korean prose, or `None` |
| Create | `src/newsletter/slices/monthly/report.py` | pure: `MonthlyReport` → markdown |
| Create | `src/newsletter/slices/monthly/cli.py` | `newsletter monthly` command |
| Create | `prompts/monthly/digest-narrative.md` | opus writer prompt |
| Modify | `src/newsletter/cli.py` | mount `monthly` sub-app |
| Modify | `AGENTS.md` | document command + slice |
| Create (tests) | `tests/slices/monthly/{__init__,test_service,test_narrative,test_report,test_cli}.py` | per-module tests |

---

### Task 1: schemas.py + service.py

**Files:**
- Create: `src/newsletter/slices/monthly/__init__.py`, `src/newsletter/slices/monthly/schemas.py`, `src/newsletter/slices/monthly/service.py`
- Create: `tests/slices/monthly/__init__.py`, `tests/slices/monthly/test_service.py`

- [ ] **Step 1: Create package markers + schemas**

Create `src/newsletter/slices/monthly/__init__.py`:

```python
"""Monthly AI digest — trends + competitors + top items + LLM narrative."""
```

Create `tests/slices/monthly/__init__.py` as an empty file (no content).

Create `src/newsletter/slices/monthly/schemas.py`:

```python
"""Schemas for the monthly AI digest report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from newsletter.slices.competitors.schemas import CompetitorReport
from newsletter.slices.trends.schemas import TrendReport


@dataclass(frozen=True, slots=True)
class TopHeadline:
    """One importance-ranked article in the digest's 주요 기사 section."""

    title: str
    url: str
    importance: float
    category: str | None
    summary: str | None  # used only as LLM narrative input, not rendered


@dataclass(frozen=True, slots=True)
class MonthlyReport:
    """Aggregated month of data plus an optional LLM narrative."""

    month: str  # "2026-04"
    since: date
    until: date  # exclusive (first day of next month)
    total_items: int
    trend: TrendReport
    competitors: CompetitorReport
    top_headlines: list[TopHeadline]  # importance desc, truncated to top_k
    narrative: str | None = None
```

- [ ] **Step 2: Write the failing service test**

Create `tests/slices/monthly/test_service.py`:

```python
"""monthly.service — calendar-month aggregation."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.monthly.service import build_monthly_report
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate


def _seed_source(db_session: Session) -> None:
    sources_repo.add(
        db_session,
        SourceCreate(
            source_id="src",
            name="src",
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
            trust_level="media",  # type: ignore[arg-type]
        ),
    )


def _seed_item(
    db_session: Session,
    *,
    title: str,
    importance: float,
    published_at: datetime,
    summary: str = "summary",
) -> None:
    raw = RawItem(
        source_id="src",
        title=title,
        url=f"https://example.com/{title[:20]}-{published_at}",
        published_at=published_at,
        raw_summary=summary,
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title=title,
            canonical_url=raw.url,
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=importance,
            summary=summary,
            keywords=None,
            duplicate_group_id=None,
        )
    )
    db_session.flush()


def test_aggregates_calendar_month(db_session: Session):
    _seed_source(db_session)
    _seed_item(db_session, title="In April A", importance=2.0, published_at=datetime(2026, 4, 10, 9, 0))
    _seed_item(db_session, title="In April B", importance=5.0, published_at=datetime(2026, 4, 20, 9, 0))
    # outside the month
    _seed_item(db_session, title="In May", importance=9.0, published_at=datetime(2026, 5, 2, 9, 0))
    db_session.commit()

    report = build_monthly_report(db_session, month=date(2026, 4, 15))
    assert report.month == "2026-04"
    assert report.since == date(2026, 4, 1)
    assert report.until == date(2026, 5, 1)
    assert report.total_items == 2  # only April items scanned
    # top headline is the highest importance within April
    assert report.top_headlines[0].title == "In April B"
    assert report.top_headlines[0].importance == 5.0
    # trend and competitors objects are populated (competitors empty -> no rows)
    assert report.trend.total_current_items >= 0
    assert report.competitors.competitors == []


def test_top_headlines_truncated_to_top_k(db_session: Session):
    _seed_source(db_session)
    for i in range(5):
        _seed_item(
            db_session, title=f"Item {i}", importance=float(i), published_at=datetime(2026, 4, 10, 9, 0)
        )
    db_session.commit()
    report = build_monthly_report(db_session, month=date(2026, 4, 1), top_k=3)
    assert report.total_items == 5
    assert len(report.top_headlines) == 3
    assert [h.importance for h in report.top_headlines] == [4.0, 3.0, 2.0]


def test_default_month_is_previous_completed_month(db_session: Session):
    # No data needed; just assert the window math for a known "today".
    from newsletter.slices.monthly.service import _month_bounds, _previous_month_first

    assert _previous_month_first(date(2026, 5, 22)) == date(2026, 4, 1)
    assert _previous_month_first(date(2026, 1, 3)) == date(2025, 12, 1)
    assert _month_bounds(date(2026, 12, 9)) == (date(2026, 12, 1), date(2027, 1, 1))


def test_empty_month_returns_zero_items(db_session: Session):
    report = build_monthly_report(db_session, month=date(2026, 4, 1))
    assert report.total_items == 0
    assert report.top_headlines == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/slices/monthly/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.monthly.service'`

- [ ] **Step 4: Write service.py**

Create `src/newsletter/slices/monthly/service.py`:

```python
"""Monthly digest aggregation over accumulated ProcessedItem rows.

Reuses the trends and competitors services for their sections, plus an
importance-ranked "top headlines" query whose ordering already reflects the
company-interest scoring boost. DB-only; the LLM narrative is added separately.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.competitors.service import analyze_competitors
from newsletter.slices.monthly.schemas import MonthlyReport, TopHeadline
from newsletter.slices.trends.service import analyze_trends


def _month_bounds(month: date) -> tuple[date, date]:
    """First day of ``month`` and first day of the next month (exclusive)."""
    since = month.replace(day=1)
    if since.month == 12:
        until = since.replace(year=since.year + 1, month=1)
    else:
        until = since.replace(month=since.month + 1)
    return since, until


def _previous_month_first(today: date) -> date:
    """First day of the month before ``today``'s month."""
    first_this = today.replace(day=1)
    return (first_this - timedelta(days=1)).replace(day=1)


def build_monthly_report(
    session: Session, *, month: date | None = None, top_k: int = 10
) -> MonthlyReport:
    """Aggregate trends + competitors + top headlines for one calendar month."""
    target = month or _previous_month_first(date.today())
    since, until = _month_bounds(target)

    trend = analyze_trends(session, period="month", end=until - timedelta(days=1))
    competitors = analyze_competitors(session, since=since, until=until, top_k=5)

    lo = datetime.combine(since, time.min)
    hi = datetime.combine(until, time.min)
    total_items = 0
    headlines: list[TopHeadline] = []
    for title, url, importance, category, summary, published_at, created_at in _fetch(
        session, lo, hi
    ):
        anchor = _anchor(published_at, created_at)
        if anchor is None or not (lo <= anchor < hi):
            continue
        total_items += 1
        headlines.append(
            TopHeadline(
                title=title,
                url=url,
                importance=importance or 0.0,
                category=category,
                summary=summary,
            )
        )
    headlines.sort(key=lambda h: h.importance, reverse=True)

    return MonthlyReport(
        month=target.strftime("%Y-%m"),
        since=since,
        until=until,
        total_items=total_items,
        trend=trend,
        competitors=competitors,
        top_headlines=headlines[:top_k],
    )


def _fetch(session: Session, lo: datetime, hi: datetime):
    """Rows whose anchor (published_at, else created_at) falls in [lo, hi)."""
    stmt = (
        select(
            ProcessedItem.normalized_title,
            ProcessedItem.canonical_url,
            ProcessedItem.importance_score,
            ProcessedItem.category,
            ProcessedItem.summary,
            RawItem.published_at,
            ProcessedItem.created_at,
        )
        .join(RawItem, RawItem.id == ProcessedItem.raw_item_id)
        .where(
            or_(
                and_(
                    RawItem.published_at.is_not(None),
                    RawItem.published_at >= lo,
                    RawItem.published_at < hi,
                ),
                and_(
                    RawItem.published_at.is_(None),
                    ProcessedItem.created_at >= lo,
                    ProcessedItem.created_at < hi,
                ),
            )
        )
    )
    return session.execute(stmt).all()


def _anchor(published_at: datetime | None, created_at: datetime | None) -> datetime | None:
    dt = published_at if published_at is not None else created_at
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


__all__ = ["build_monthly_report"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/slices/monthly/test_service.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/monthly tests/slices/monthly
uv run ruff format src/newsletter/slices/monthly tests/slices/monthly
git add src/newsletter/slices/monthly tests/slices/monthly
git commit -m "feat(monthly): schemas + calendar-month aggregation service"
```

---

### Task 2: prompt + narrative.py

**Files:**
- Create: `prompts/monthly/digest-narrative.md`
- Create: `src/newsletter/slices/monthly/narrative.py`
- Test: `tests/slices/monthly/test_narrative.py`

- [ ] **Step 1: Create the prompt**

Create `prompts/monthly/digest-narrative.md`:

```markdown
---
name: monthly-digest-narrative
model: claude-opus-4-7
version: 1
inputs: [month, digest_json]
---

You are the editor of an internal monthly AI intelligence report for an
enterprise audience (engineers, PMs, AI practitioners). You write the
"이번 달 요약" narrative in Korean markdown prose.

대상 월: {month}

집계 데이터(JSON — 떠오르는/신규 용어, 경쟁사 멘션 수, 주요 기사 제목과 요약 일부):
{digest_json}

지침:
- 위 데이터에 근거해서만 작성합니다. 데이터에 없는 수치나 사실을 지어내지 마세요.
- 2~4개의 짧은 한국어 문단으로 이번 달 흐름을 요약합니다.
- 제목(#, ##)이나 표, 코드 펜스, 잡담은 출력하지 마세요. 문단 산문만 출력합니다.
```

- [ ] **Step 2: Write the failing narrative test**

Create `tests/slices/monthly/test_narrative.py`:

```python
"""monthly.narrative — LLM digest summary (fake client, no real calls)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from newsletter.core.llm import LLMError, LLMResponse
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.monthly.narrative import build_narrative
from newsletter.slices.monthly.service import build_monthly_report
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate


class _FakeLLM:
    def __init__(self, *, text: str = "이번 달은 ...", error: bool = False) -> None:
        self.text = text
        self.error = error
        self.last_body: str | None = None

    def complete(self, body: str, *, model: str, max_tokens: int) -> LLMResponse:
        self.last_body = body
        if self.error:
            raise LLMError("boom")
        return LLMResponse(text=self.text, model=model, input_tokens=1, output_tokens=1)


def _report_with_one_item(db_session: Session):
    sources_repo.add(
        db_session,
        SourceCreate(
            source_id="src",
            name="src",
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
            trust_level="media",  # type: ignore[arg-type]
        ),
    )
    raw = RawItem(
        source_id="src",
        title="GPT-5 launch",
        url="https://example.com/x",
        published_at=datetime(2026, 4, 10, 9, 0),
        raw_summary="secret body text",
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title="GPT-5 launch",
            canonical_url="https://example.com/x",
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=3.0,
            summary="short summary",
        )
    )
    db_session.commit()
    return build_monthly_report(db_session, month=date(2026, 4, 1))


def test_returns_narrative_text(db_session: Session):
    report = _report_with_one_item(db_session)
    fake = _FakeLLM(text="이번 달 요약 내용")
    out = build_narrative(report, llm=fake)
    assert out == "이번 달 요약 내용"


def test_llm_error_returns_none(db_session: Session):
    report = _report_with_one_item(db_session)
    out = build_narrative(report, llm=_FakeLLM(error=True))
    assert out is None


def test_prompt_input_uses_titles_not_full_summary_field_name(db_session: Session):
    report = _report_with_one_item(db_session)
    fake = _FakeLLM()
    build_narrative(report, llm=fake)
    # the headline title is sent; the prompt is built from the digest JSON
    assert "GPT-5 launch" in fake.last_body
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/slices/monthly/test_narrative.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.monthly.narrative'`

- [ ] **Step 4: Write narrative.py**

Create `src/newsletter/slices/monthly/narrative.py`:

```python
"""LLM narrative ("이번 달 요약") for the monthly digest.

Feeds the deterministic digest (top terms, competitor mention counts, top
headline titles + truncated summaries) to the writer model and returns prose
markdown. Title + truncated summary only — never full article bodies. Returns
``None`` when the LLM is unavailable so the rest of the report still renders.
"""

from __future__ import annotations

import json
from typing import Any

from newsletter.core.llm import LLMClient, LLMError
from newsletter.core.logging import get_logger
from newsletter.core.prompts import load_prompt
from newsletter.slices.monthly.schemas import MonthlyReport

log = get_logger(__name__)

_PROMPT = "monthly/digest-narrative.md"
_SUMMARY_CHARS = 300


def build_narrative(report: MonthlyReport, *, llm: LLMClient) -> str | None:
    """Generate the Korean narrative section, or ``None`` if the LLM fails."""
    prompt = load_prompt(_PROMPT)
    digest_json = json.dumps(_digest_input(report), ensure_ascii=False)
    body = prompt.render(month=report.month, digest_json=digest_json)
    try:
        response = llm.complete(body, model=prompt.model, max_tokens=2048)
    except LLMError as exc:
        log.warning("monthly.narrative.failed", error=str(exc))
        return None
    return response.text.strip() or None


def _digest_input(report: MonthlyReport) -> dict[str, Any]:
    return {
        "rising_terms": [d.term for d in report.trend.rising[:10]],
        "new_terms": [d.term for d in report.trend.new[:10]],
        "competitors": [
            {"name": m.name, "count": m.count} for m in report.competitors.competitors
        ],
        "top_headlines": [
            {
                "title": h.title,
                "category": h.category,
                "summary": (h.summary or "")[:_SUMMARY_CHARS],
            }
            for h in report.top_headlines
        ],
    }


__all__ = ["build_narrative"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/slices/monthly/test_narrative.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/monthly tests/slices/monthly
uv run ruff format src/newsletter/slices/monthly tests/slices/monthly
git add src/newsletter/slices/monthly tests/slices/monthly prompts/monthly
git commit -m "feat(monthly): LLM narrative summary (opus, graceful fallback)"
```

---

### Task 3: report.py

**Files:**
- Create: `src/newsletter/slices/monthly/report.py`
- Test: `tests/slices/monthly/test_report.py`

- [ ] **Step 1: Write the failing report test**

Create `tests/slices/monthly/test_report.py`:

```python
"""monthly.report — deterministic markdown rendering."""

from __future__ import annotations

from datetime import date

from newsletter.slices.competitors.schemas import (
    CompetitorMentions,
    CompetitorReport,
)
from newsletter.slices.monthly.report import render_markdown
from newsletter.slices.monthly.schemas import MonthlyReport, TopHeadline
from newsletter.slices.trends.schemas import TermDelta, TrendReport, WindowSpec


def _trend(*, rising=(), new=(), top=()) -> TrendReport:
    w = WindowSpec(
        period="month",
        current_start=date(2026, 4, 1),
        current_end=date(2026, 5, 1),
        previous_start=date(2026, 3, 1),
        previous_end=date(2026, 4, 1),
    )
    mk = lambda t: TermDelta(term=t, current=3, previous=0, delta=3, importance=1.0)
    return TrendReport(
        window=w,
        rising=[mk(t) for t in rising],
        fading=[],
        new=[mk(t) for t in new],
        dropped=[],
        top_current=[mk(t) for t in top],
        total_current_items=3,
        total_previous_items=0,
    )


def _report(*, narrative=None, rising=(), competitors=(), headlines=()) -> MonthlyReport:
    return MonthlyReport(
        month="2026-04",
        since=date(2026, 4, 1),
        until=date(2026, 5, 1),
        total_items=10,
        trend=_trend(rising=rising),
        competitors=CompetitorReport(
            since=date(2026, 4, 1),
            until=date(2026, 5, 1),
            total_items=10,
            competitors=[CompetitorMentions(name=n, count=c, headlines=[]) for n, c in competitors],
        ),
        top_headlines=[
            TopHeadline(title=t, url=u, importance=1.0, category=None, summary=None)
            for t, u in headlines
        ],
        narrative=narrative,
    )


def test_header_and_sections_present():
    md = render_markdown(_report())
    assert "# 2026-04 AI 동향 리포트" in md
    assert "## 이번 달 요약" in md
    assert "## 트렌드" in md
    assert "## 경쟁사 동향" in md
    assert "## 주요 기사" in md
    assert "2026-04-01" in md and "2026-05-01" in md


def test_narrative_fallback_when_none():
    md = render_markdown(_report(narrative=None))
    assert "(요약 생략 — LLM 비활성)" in md


def test_narrative_rendered_when_present():
    md = render_markdown(_report(narrative="이번 달은 멀티모달이 화제였습니다."))
    assert "이번 달은 멀티모달이 화제였습니다." in md
    assert "(요약 생략" not in md


def test_sections_render_data_and_empty_markers():
    md = render_markdown(
        _report(
            rising=("sora", "gpt"),
            competitors=[("OpenAI", 5)],
            headlines=[("Big news", "https://e.com/a")],
        )
    )
    assert "떠오르는: sora, gpt" in md
    assert "- OpenAI: 5건" in md
    assert "[Big news](https://e.com/a)" in md

    empty = render_markdown(_report())
    assert "(데이터 없음)" in empty       # trends
    assert "(경쟁사 미등록)" in empty      # competitors
    assert "(기사 없음)" in empty          # headlines
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/slices/monthly/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.monthly.report'`

- [ ] **Step 3: Write report.py**

Create `src/newsletter/slices/monthly/report.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/slices/monthly/test_report.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/monthly tests/slices/monthly
uv run ruff format src/newsletter/slices/monthly tests/slices/monthly
git add src/newsletter/slices/monthly tests/slices/monthly
git commit -m "feat(monthly): markdown report rendering"
```

---

### Task 4: cli.py + root registration

**Files:**
- Create: `src/newsletter/slices/monthly/cli.py`
- Modify: `src/newsletter/cli.py`
- Test: `tests/slices/monthly/test_cli.py`

- [ ] **Step 1: Write the failing CLI test**

Create `tests/slices/monthly/test_cli.py`:

```python
"""monthly CLI smoke tests. ANTHROPIC_API_KEY is blank in tests, so the
narrative is skipped automatically — output is deterministic."""

from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.monthly.cli import app
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

runner = CliRunner()


def _seed(db_session) -> None:
    sources_repo.add(
        db_session,
        SourceCreate(
            source_id="src",
            name="src",
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
            trust_level="media",  # type: ignore[arg-type]
        ),
    )
    raw = RawItem(
        source_id="src",
        title="April headline",
        url="https://example.com/x",
        published_at=datetime(2026, 4, 10, 9, 0),
        raw_summary="news",
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title="April headline",
            canonical_url="https://example.com/x",
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=1.0,
            summary="news",
        )
    )
    db_session.commit()


def test_monthly_smoke(db_session):
    _seed(db_session)
    result = runner.invoke(app, ["--month", "2026-04"])
    assert result.exit_code == 0, result.output
    assert "2026-04 AI 동향 리포트" in result.output
    assert "April headline" in result.output
    # no API key in tests -> narrative skipped
    assert "(요약 생략 — LLM 비활성)" in result.output


def test_monthly_html_format(db_session):
    _seed(db_session)
    result = runner.invoke(app, ["--month", "2026-04", "--format", "html"])
    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("<!DOCTYPE html>")
    assert "AI 동향 리포트" in result.output


def test_monthly_save_to_file(tmp_path, db_session):
    _seed(db_session)
    out = tmp_path / "digest.md"
    result = runner.invoke(app, ["--month", "2026-04", "--save", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "AI 동향 리포트" in out.read_text(encoding="utf-8")


def test_monthly_rejects_bad_format(db_session):
    result = runner.invoke(app, ["--month", "2026-04", "--format", "pdf"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/slices/monthly/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.monthly.cli'`

- [ ] **Step 3: Write cli.py**

Create `src/newsletter/slices/monthly/cli.py`:

```python
"""``newsletter monthly`` — monthly AI digest.

Aggregates trends + competitor mentions + importance-ranked top items for a
calendar month, optionally adds an LLM narrative (skipped when no API key or
``--no-narrative``), and prints/saves markdown or HTML.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date as date_cls
from pathlib import Path

import typer

from newsletter.core.config import get_settings
from newsletter.core.db import session_scope
from newsletter.core.report_html import render_report_html
from newsletter.slices.monitoring.recorder import build_llm_client
from newsletter.slices.monthly.narrative import build_narrative
from newsletter.slices.monthly.report import render_markdown
from newsletter.slices.monthly.service import build_monthly_report

app = typer.Typer(
    name="monthly",
    help="Monthly AI digest: trends + competitors + top items + LLM narrative.",
    invoke_without_command=True,
    no_args_is_help=False,
)


def _resolve_month(value: str | None) -> date_cls | None:
    if not value:
        return None
    return date_cls.fromisoformat(f"{value}-01")


@app.callback(invoke_without_command=True)
def cmd_monthly(
    month: str | None = typer.Option(
        None, "--month", help="Target month YYYY-MM (default: last completed month)."
    ),
    top: int = typer.Option(10, "--top", help="Max headlines in the 주요 기사 section."),
    no_narrative: bool = typer.Option(
        False, "--no-narrative", help="Skip the LLM narrative section."
    ),
    fmt: str = typer.Option("md", "--format", help="md or html."),
    save: str | None = typer.Option(
        None, "--save", help="Write the report to this path instead of stdout."
    ),
) -> None:
    """Print (or save) the monthly AI digest."""
    if fmt not in ("md", "html"):
        typer.echo("format must be 'md' or 'html'", err=True)
        raise typer.Exit(code=1)
    try:
        target = _resolve_month(month)
    except ValueError:
        typer.echo("month must be YYYY-MM", err=True)
        raise typer.Exit(code=1) from None

    with session_scope() as session:
        report = build_monthly_report(session, month=target, top_k=top)

    if not no_narrative and get_settings().anthropic_api_key:
        report = replace(report, narrative=build_narrative(report, llm=build_llm_client()))

    markdown = render_markdown(report)
    output = (
        render_report_html(markdown, title=f"{report.month} AI 동향 리포트")
        if fmt == "html"
        else markdown
    )
    if save:
        Path(save).write_text(output, encoding="utf-8")
        typer.echo(f"월간 리포트 저장: {save}")
    else:
        typer.echo(output)
```

- [ ] **Step 4: Register the sub-app in the root CLI**

Edit `src/newsletter/cli.py`. Add the import alphabetically among the slice imports (after the `monitoring` import line `from newsletter.slices.monitoring.cli import app as stats_app  # noqa: E402`):

```python
from newsletter.slices.monthly.cli import app as monthly_app  # noqa: E402
```

Add the mount after `app.add_typer(stats_app, name="stats")`:

```python
app.add_typer(monthly_app, name="monthly")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/slices/monthly/test_cli.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Verify root wiring**

Run: `uv run newsletter monthly --help`
Expected: help text showing `--month`, `--top`, `--no-narrative`, `--format`, `--save`.

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/monthly src/newsletter/cli.py tests/slices/monthly
uv run ruff format src/newsletter/slices/monthly src/newsletter/cli.py tests/slices/monthly
git add src/newsletter/slices/monthly src/newsletter/cli.py tests/slices/monthly
git commit -m "feat(monthly): CLI command + root registration"
```

---

### Task 5: AGENTS.md docs + full verification

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Add the command row**

Edit `AGENTS.md`. After the `competitors` command row, add:

```markdown
| `uv run newsletter monthly [--month YYYY-MM] [--top K] [--no-narrative] [--format md\|html] [--save PATH]` | Monthly AI digest — trends + competitors + top items + LLM narrative |
```

- [ ] **Step 2: Add the slice-tree entry**

Edit `AGENTS.md`. The slice tree currently ends with `competitors/` as the last child (`└──`). Change `competitors/` to `├──` and add `monthly/` as the new last child (`└──`):

```markdown
│   ├── competitors/     운영자가 등록한 경쟁사(이름+별칭)를 누적 ProcessedItem에서 탐지해 멘션 수·대표 헤드라인을 보여주는 독립 리포트 슬라이스
│   └── monthly/         한 달치 트렌드·경쟁사·중요도 상위 기사를 종합하고 LLM 서술 요약을 얹는 월간 리포트 슬라이스
```

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -q`
Expected: all pass. Prior baseline was 598; this adds ~15 (4 service + 3 narrative + 4 report + 4 cli), so expect ~613 passing, 0 failed.

- [ ] **Step 4: Manual smoke**

Run: `uv run newsletter monthly --month 2026-04 --no-narrative`
Expected: prints a markdown report headed `# 2026-04 AI 동향 리포트` with the four sections (likely mostly empty markers against an empty dev DB — that's fine).

- [ ] **Step 5: Lint check**

Run: `uv run ruff check src/newsletter/slices/monthly src/newsletter/cli.py tests/slices/monthly`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md
git commit -m "docs(monthly): document command + slice in AGENTS.md"
```

---

## Self-Review Notes

- **Spec coverage:** new `monthly` slice (Tasks 1–4); calendar-month window (`_month_bounds`/`_previous_month_first`, Task 1); reuse trends + competitors (Task 1 service); importance-ranked top headlines = the "interests" reflection (Task 1); LLM narrative opus + graceful None (Task 2); markdown render with section fallbacks (Task 3); HTML via Stage-1 renderer + `--format`/`--no-narrative`/`--month`/`--save` (Task 4); docs (Task 5). All design sections map to a task.
- **Type consistency:** `MonthlyReport`/`TopHeadline` defined in Task 1 and consumed by service/narrative/report/cli. `build_monthly_report(session, *, month, top_k)`, `build_narrative(report, *, llm)`, `render_markdown(report)`, `render_report_html(md, *, title)` signatures are used identically wherever called. `TopHeadline.summary` (added for narrative input) is populated in service and read in narrative; report does not render it. CLI param `fmt`/`--format` matches the Stage-1 convention.
- **No placeholders:** every code step shows complete code; every run step has an exact command and expected outcome.
- **Test determinism:** `ANTHROPIC_API_KEY` is blanked by the test fixture, so CLI tests skip the narrative and never make a real LLM call; narrative tests inject a `_FakeLLM`. Service/report tests are pure/DB-seeded.
</content>
