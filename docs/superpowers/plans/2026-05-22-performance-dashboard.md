# Performance Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `dashboard` slice that reports per-source performance (collected vs processed, average scores) and quality metrics (track split, top categories, dedup) over a look-back window, as markdown or HTML.

**Architecture:** A new vertical slice `dashboard/{schemas,service,report,cli}.py`. `service` runs one read-only window query (`RawItem` LEFT JOIN `ProcessedItem`, filtered on the indexed `RawItem.collected_at`) and aggregates in Python; `report` renders markdown; HTML is derived via the existing `core/report_html`. No LLM, no new tables. Complements `newsletter stats` (operational/cost from RunLog).

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Typer, `markdown-it-py`, pytest.

---

## Design Source

Full design: `docs/superpowers/specs/2026-05-22-performance-dashboard-design.md`. Brainstorming complete — do not re-brainstorm. Click/open-rate metrics are out of scope (no tracking data exists).

## File Structure

| Kind | Path | Responsibility |
|---|---|---|
| Create | `src/newsletter/slices/dashboard/__init__.py` | package marker |
| Create | `src/newsletter/slices/dashboard/schemas.py` | `SourceStat`, `QualitySummary`, `DashboardReport` dataclasses |
| Create | `src/newsletter/slices/dashboard/service.py` | DB: window aggregation → `DashboardReport` |
| Create | `src/newsletter/slices/dashboard/report.py` | pure: `DashboardReport` → markdown |
| Create | `src/newsletter/slices/dashboard/cli.py` | `newsletter dashboard` command |
| Modify | `src/newsletter/cli.py` | mount `dashboard` sub-app |
| Modify | `AGENTS.md` | document command + slice |
| Create (tests) | `tests/slices/dashboard/{__init__,test_service,test_report,test_cli}.py` | per-module tests |

---

### Task 1: schemas.py + service.py

**Files:**
- Create: `src/newsletter/slices/dashboard/__init__.py`, `src/newsletter/slices/dashboard/schemas.py`, `src/newsletter/slices/dashboard/service.py`
- Create: `tests/slices/dashboard/__init__.py`, `tests/slices/dashboard/test_service.py`

- [ ] **Step 1: Create package markers + schemas**

Create `src/newsletter/slices/dashboard/__init__.py`:

```python
"""Performance dashboard — per-source yield + quality metrics report."""
```

Create `tests/slices/dashboard/__init__.py` as an empty file (no content).

Create `src/newsletter/slices/dashboard/schemas.py`:

```python
"""Schemas for the performance dashboard report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class SourceStat:
    """Per-source yield and average quality within the window."""

    source_id: str
    name: str
    content_track: str
    collected: int
    processed: int
    avg_relevance: float  # 0.0 when processed == 0
    avg_importance: float


@dataclass(frozen=True, slots=True)
class QualitySummary:
    """Window-wide quality rollup."""

    total_collected: int
    total_processed: int
    track_counts: dict[str, int]  # content_track -> processed count
    top_categories: list[tuple[str, int]]  # (category, count) desc, top_k
    distinct_groups: int  # distinct non-null duplicate_group_id
    grouped_items: int  # processed items carrying a duplicate_group_id


@dataclass(frozen=True, slots=True)
class DashboardReport:
    since: date
    until: date  # exclusive
    sources: list[SourceStat]  # collected desc, then name
    quality: QualitySummary
```

- [ ] **Step 2: Write the failing service test**

Create `tests/slices/dashboard/test_service.py`:

```python
"""dashboard.service — window aggregation over collected/processed items."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.dashboard.service import build_dashboard
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

_UNTIL = date(2026, 5, 22)


def _seed_source(db_session: Session, source_id: str = "src", name: str = "Src") -> None:
    sources_repo.add(
        db_session,
        SourceCreate(
            source_id=source_id,
            name=name,
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
            trust_level="media",  # type: ignore[arg-type]
        ),
    )


def _seed_raw(
    db_session: Session,
    *,
    source_id: str = "src",
    title: str,
    collected_at: datetime,
) -> RawItem:
    raw = RawItem(
        source_id=source_id,
        title=title,
        url=f"https://example.com/{source_id}/{title}",
        published_at=collected_at,
        collected_at=collected_at,
        raw_summary=title,
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    return raw


def _process(
    db_session: Session,
    raw: RawItem,
    *,
    relevance: float,
    importance: float,
    track: str = "expert_news",
    category: str | None = "AI Model",
    group: str | None = None,
) -> None:
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title=raw.title,
            canonical_url=raw.url,
            content_track=track,
            category=category,
            relevance_score=relevance,
            importance_score=importance,
            summary=raw.title,
            keywords=None,
            duplicate_group_id=group,
        )
    )
    db_session.flush()


def test_per_source_yield_and_avg_scores(db_session: Session):
    _seed_source(db_session)
    r1 = _seed_raw(db_session, title="a", collected_at=datetime(2026, 5, 20, 9, 0))
    r2 = _seed_raw(db_session, title="b", collected_at=datetime(2026, 5, 20, 10, 0))
    _process(db_session, r1, relevance=0.8, importance=2.0)
    _process(db_session, r2, relevance=0.4, importance=4.0)
    db_session.commit()

    report = build_dashboard(db_session, days=7, until=_UNTIL)
    assert len(report.sources) == 1
    s = report.sources[0]
    assert s.collected == 2
    assert s.processed == 2
    assert s.avg_relevance == 0.6  # (0.8 + 0.4) / 2
    assert s.avg_importance == 3.0  # (2.0 + 4.0) / 2


def test_unprocessed_rawitem_counted_as_collected_only(db_session: Session):
    _seed_source(db_session)
    _seed_raw(db_session, title="unprocessed", collected_at=datetime(2026, 5, 20, 9, 0))
    db_session.commit()
    report = build_dashboard(db_session, days=7, until=_UNTIL)
    s = report.sources[0]
    assert s.collected == 1
    assert s.processed == 0
    assert s.avg_relevance == 0.0
    assert s.avg_importance == 0.0
    assert report.quality.total_collected == 1
    assert report.quality.total_processed == 0


def test_window_filtering(db_session: Session):
    _seed_source(db_session)
    _seed_raw(db_session, title="in", collected_at=datetime(2026, 5, 20, 9, 0))
    _seed_raw(db_session, title="old", collected_at=datetime(2026, 4, 1, 9, 0))
    db_session.commit()
    report = build_dashboard(db_session, days=7, until=_UNTIL)
    assert report.quality.total_collected == 1  # only the in-window raw


def test_quality_summary(db_session: Session):
    _seed_source(db_session)
    r1 = _seed_raw(db_session, title="a", collected_at=datetime(2026, 5, 20, 9, 0))
    r2 = _seed_raw(db_session, title="b", collected_at=datetime(2026, 5, 20, 10, 0))
    r3 = _seed_raw(db_session, title="c", collected_at=datetime(2026, 5, 20, 11, 0))
    _process(db_session, r1, relevance=0.9, importance=1.0, track="expert_news", category="LLM", group="g1")
    _process(db_session, r2, relevance=0.9, importance=1.0, track="expert_news", category="LLM", group="g1")
    _process(db_session, r3, relevance=0.9, importance=1.0, track="practical_insight", category="Tooling", group=None)
    db_session.commit()

    q = build_dashboard(db_session, days=7, until=_UNTIL).quality
    assert q.total_processed == 3
    assert q.track_counts == {"expert_news": 2, "practical_insight": 1}
    assert q.top_categories[0] == ("LLM", 2)
    assert q.distinct_groups == 1   # only "g1"
    assert q.grouped_items == 2     # r1 + r2 carry a group id


def test_empty_window(db_session: Session):
    report = build_dashboard(db_session, days=7, until=_UNTIL)
    assert report.sources == []
    assert report.quality.total_collected == 0
    assert report.quality.top_categories == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/slices/dashboard/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.dashboard.service'`

- [ ] **Step 4: Write service.py**

Create `src/newsletter/slices/dashboard/service.py`:

```python
"""Performance dashboard aggregation over collected/processed items.

Read-only. Computes per-source yield (collected vs processed) and quality
(average scores, track split, top categories, dedup effectiveness) for one
look-back window on the indexed ``RawItem.collected_at``. Complements
``newsletter stats``, which covers operational/cost metrics from RunLog.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source
from newsletter.slices.dashboard.schemas import (
    DashboardReport,
    QualitySummary,
    SourceStat,
)


def build_dashboard(
    session: Session,
    *,
    days: int = 30,
    until: date | None = None,
    since: date | None = None,
    top_categories: int = 10,
) -> DashboardReport:
    """Aggregate per-source yield + quality for one look-back window."""
    until_date = until or (date.today() + timedelta(days=1))
    since_date = since or (until_date - timedelta(days=days))
    lo = datetime.combine(since_date, time.min)
    hi = datetime.combine(until_date, time.min)

    meta = {
        sid: (name, track)
        for sid, name, track in session.execute(
            select(Source.source_id, Source.name, Source.content_track)
        ).all()
    }

    rows = session.execute(
        select(
            RawItem.source_id,
            ProcessedItem.id,
            ProcessedItem.relevance_score,
            ProcessedItem.importance_score,
            ProcessedItem.content_track,
            ProcessedItem.category,
            ProcessedItem.duplicate_group_id,
        )
        .select_from(RawItem)
        .join(ProcessedItem, ProcessedItem.raw_item_id == RawItem.id, isouter=True)
        .where(RawItem.collected_at >= lo, RawItem.collected_at < hi)
    ).all()

    collected: dict[str, int] = {}
    processed: dict[str, int] = {}
    rel_sum: dict[str, float] = {}
    imp_sum: dict[str, float] = {}

    total_collected = 0
    total_processed = 0
    track_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    groups: set[str] = set()
    grouped_items = 0

    for sid, pid, rel, imp, track, category, dgid in rows:
        total_collected += 1
        collected[sid] = collected.get(sid, 0) + 1
        if pid is not None:
            total_processed += 1
            processed[sid] = processed.get(sid, 0) + 1
            rel_sum[sid] = rel_sum.get(sid, 0.0) + (rel or 0.0)
            imp_sum[sid] = imp_sum.get(sid, 0.0) + (imp or 0.0)
            if track:
                track_counts[track] = track_counts.get(track, 0) + 1
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
            if dgid:
                groups.add(dgid)
                grouped_items += 1

    sources: list[SourceStat] = []
    for sid, count in collected.items():
        proc = processed.get(sid, 0)
        name, track = meta.get(sid, (sid, "?"))
        sources.append(
            SourceStat(
                source_id=sid,
                name=name,
                content_track=track,
                collected=count,
                processed=proc,
                avg_relevance=(rel_sum.get(sid, 0.0) / proc) if proc else 0.0,
                avg_importance=(imp_sum.get(sid, 0.0) / proc) if proc else 0.0,
            )
        )
    sources.sort(key=lambda s: (-s.collected, s.name))

    top_cats = sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0]))[
        :top_categories
    ]

    return DashboardReport(
        since=since_date,
        until=until_date,
        sources=sources,
        quality=QualitySummary(
            total_collected=total_collected,
            total_processed=total_processed,
            track_counts=track_counts,
            top_categories=top_cats,
            distinct_groups=len(groups),
            grouped_items=grouped_items,
        ),
    )


__all__ = ["build_dashboard"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/slices/dashboard/test_service.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/dashboard tests/slices/dashboard
uv run ruff format src/newsletter/slices/dashboard tests/slices/dashboard
git add src/newsletter/slices/dashboard tests/slices/dashboard
git commit -m "feat(dashboard): schemas + source/quality aggregation service"
```

---

### Task 2: report.py

**Files:**
- Create: `src/newsletter/slices/dashboard/report.py`
- Test: `tests/slices/dashboard/test_report.py`

- [ ] **Step 1: Write the failing report test**

Create `tests/slices/dashboard/test_report.py`:

```python
"""dashboard.report — deterministic markdown rendering."""

from __future__ import annotations

from datetime import date

from newsletter.slices.dashboard.report import render_markdown
from newsletter.slices.dashboard.schemas import (
    DashboardReport,
    QualitySummary,
    SourceStat,
)


def _report(*, sources=(), quality=None) -> DashboardReport:
    return DashboardReport(
        since=date(2026, 5, 15),
        until=date(2026, 5, 22),
        sources=list(sources),
        quality=quality
        or QualitySummary(
            total_collected=0,
            total_processed=0,
            track_counts={},
            top_categories=[],
            distinct_groups=0,
            grouped_items=0,
        ),
    )


def test_header_period():
    md = render_markdown(_report())
    assert "# 성과 대시보드" in md
    assert "2026-05-15" in md and "2026-05-22" in md


def test_source_table_rendered():
    s = SourceStat(
        source_id="src",
        name="My Source",
        content_track="expert_news",
        collected=10,
        processed=7,
        avg_relevance=0.83,
        avg_importance=2.5,
    )
    md = render_markdown(_report(sources=[s]))
    assert "## 소스별 성과" in md
    assert "My Source" in md
    assert "| My Source | expert_news | 10 | 7 | 0.83 | 2.50 |" in md


def test_quality_summary_rendered():
    q = QualitySummary(
        total_collected=20,
        total_processed=12,
        track_counts={"expert_news": 8, "practical_insight": 4},
        top_categories=[("LLM", 5), ("Tooling", 3)],
        distinct_groups=2,
        grouped_items=6,
    )
    md = render_markdown(_report(quality=q))
    assert "전체 수집: 20건 / 처리: 12건" in md
    assert "expert_news: 8" in md and "practical_insight: 4" in md
    assert "그룹화 6건 / 고유 그룹 2개" in md
    assert "| LLM | 5 |" in md


def test_empty_markers():
    md = render_markdown(_report())
    assert "(데이터 없음)" in md  # no sources
    assert "(없음)" in md          # no categories
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/slices/dashboard/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.dashboard.report'`

- [ ] **Step 3: Write report.py**

Create `src/newsletter/slices/dashboard/report.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/slices/dashboard/test_report.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/dashboard tests/slices/dashboard
uv run ruff format src/newsletter/slices/dashboard tests/slices/dashboard
git add src/newsletter/slices/dashboard tests/slices/dashboard
git commit -m "feat(dashboard): markdown report rendering"
```

---

### Task 3: cli.py + root registration

**Files:**
- Create: `src/newsletter/slices/dashboard/cli.py`
- Modify: `src/newsletter/cli.py`
- Test: `tests/slices/dashboard/test_cli.py`

- [ ] **Step 1: Write the failing CLI test**

Create `tests/slices/dashboard/test_cli.py`:

```python
"""dashboard CLI smoke tests."""

from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.dashboard.cli import app
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

runner = CliRunner()


def _seed(db_session) -> None:
    sources_repo.add(
        db_session,
        SourceCreate(
            source_id="src",
            name="My Source",
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
            trust_level="media",  # type: ignore[arg-type]
        ),
    )
    raw = RawItem(
        source_id="src",
        title="headline",
        url="https://example.com/x",
        published_at=datetime(2026, 5, 20, 9, 0),
        collected_at=datetime(2026, 5, 20, 9, 0),
        raw_summary="news",
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title="headline",
            canonical_url="https://example.com/x",
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=1.0,
            summary="news",
        )
    )
    db_session.commit()


def test_dashboard_smoke(db_session):
    _seed(db_session)
    result = runner.invoke(app, ["--since", "2026-05-15", "--until", "2026-05-22"])
    assert result.exit_code == 0, result.output
    assert "성과 대시보드" in result.output
    assert "My Source" in result.output


def test_dashboard_html_format(db_session):
    _seed(db_session)
    result = runner.invoke(
        app, ["--since", "2026-05-15", "--until", "2026-05-22", "--format", "html"]
    )
    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("<!DOCTYPE html>")
    assert "성과 대시보드" in result.output


def test_dashboard_save_to_file(tmp_path, db_session):
    _seed(db_session)
    out = tmp_path / "dash.md"
    result = runner.invoke(
        app, ["--since", "2026-05-15", "--until", "2026-05-22", "--save", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "성과 대시보드" in out.read_text(encoding="utf-8")


def test_dashboard_rejects_bad_format(db_session):
    result = runner.invoke(app, ["--format", "pdf"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/slices/dashboard/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.dashboard.cli'`

- [ ] **Step 3: Write cli.py**

Create `src/newsletter/slices/dashboard/cli.py`:

```python
"""``newsletter dashboard`` — source performance + quality metrics.

Deterministic report over collected/processed items in a look-back window.
No LLM. Complements ``newsletter stats`` (operational/cost).
"""

from __future__ import annotations

from datetime import date as date_cls
from pathlib import Path

import typer

from newsletter.core.db import session_scope
from newsletter.core.report_html import render_report_html
from newsletter.slices.dashboard.report import render_markdown
from newsletter.slices.dashboard.service import build_dashboard

app = typer.Typer(
    name="dashboard",
    help="Source performance + quality metrics over collected/processed items.",
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def cmd_dashboard(
    days: int = typer.Option(30, "--days", help="Look-back window length in days."),
    since: str | None = typer.Option(
        None, "--since", help="Window start YYYY-MM-DD (wins over --days)."
    ),
    until: str | None = typer.Option(
        None, "--until", help="Exclusive window end YYYY-MM-DD (default tomorrow)."
    ),
    top: int = typer.Option(10, "--top", help="Max categories in the 상위 카테고리 table."),
    fmt: str = typer.Option("md", "--format", help="md or html."),
    save: str | None = typer.Option(
        None, "--save", help="Write the report to this path instead of stdout."
    ),
) -> None:
    """Print (or save) the performance dashboard."""
    if fmt not in ("md", "html"):
        typer.echo("format must be 'md' or 'html'", err=True)
        raise typer.Exit(code=1)
    since_date = date_cls.fromisoformat(since) if since else None
    until_date = date_cls.fromisoformat(until) if until else None
    with session_scope() as session:
        report = build_dashboard(
            session, days=days, until=until_date, since=since_date, top_categories=top
        )

    markdown = render_markdown(report)
    output = (
        render_report_html(markdown, title="성과 대시보드")
        if fmt == "html"
        else markdown
    )
    if save:
        Path(save).write_text(output, encoding="utf-8")
        typer.echo(f"대시보드 저장: {save}")
    else:
        typer.echo(output)
```

- [ ] **Step 4: Register the sub-app in the root CLI**

Edit `src/newsletter/cli.py`. Add the import alphabetically among the slice imports (right after `from newsletter.slices.corpus.cli import app as corpus_app  # noqa: E402`):

```python
from newsletter.slices.dashboard.cli import app as dashboard_app  # noqa: E402
```

Add the mount after `app.add_typer(corpus_app, name="corpus")`:

```python
app.add_typer(dashboard_app, name="dashboard")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/slices/dashboard/test_cli.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Verify root wiring**

Run: `uv run newsletter dashboard --help`
Expected: help text showing `--days`, `--since`, `--until`, `--top`, `--format`, `--save`.

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/dashboard src/newsletter/cli.py tests/slices/dashboard
uv run ruff format src/newsletter/slices/dashboard src/newsletter/cli.py tests/slices/dashboard
git add src/newsletter/slices/dashboard src/newsletter/cli.py tests/slices/dashboard
git commit -m "feat(dashboard): CLI command + root registration"
```

---

### Task 4: AGENTS.md docs + full verification

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Add the command row**

Edit `AGENTS.md`. After the `monthly` command row, add:

```markdown
| `uv run newsletter dashboard [--days N \| --since DATE] [--until DATE] [--top K] [--format md\|html] [--save PATH]` | Source performance (collected/processed/scores) + quality metrics |
```

- [ ] **Step 2: Add the slice-tree entry**

Edit `AGENTS.md`. The slice tree currently ends with `monthly/` as the last child (`└──`). Change `monthly/` to `├──` and add `dashboard/` as the new last child (`└──`):

```markdown
│   ├── monthly/         한 달치 트렌드·경쟁사·중요도 상위 기사를 종합하고 LLM 서술 요약을 얹는 월간 리포트 슬라이스
│   └── dashboard/       소스별 수집·처리·평균 점수와 품질 지표(트랙·카테고리·중복)를 보여주는 성과 리포트 슬라이스
```

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -q`
Expected: all pass. Prior baseline was 613; this adds ~13 (5 service + 4 report + 4 cli), so expect ~626 passing, 0 failed.

- [ ] **Step 4: Manual smoke**

Run: `uv run newsletter dashboard --days 3650`
Expected: prints `# 성과 대시보드` with the 소스별 성과 / 품질 요약 sections (mostly empty markers against an empty dev DB — that's fine).

- [ ] **Step 5: Lint check**

Run: `uv run ruff check src/newsletter/slices/dashboard src/newsletter/cli.py tests/slices/dashboard`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md
git commit -m "docs(dashboard): document command + slice in AGENTS.md"
```

---

## Self-Review Notes

- **Spec coverage:** new `dashboard` slice (Tasks 1–3); per-source collected/processed/avg scores via LEFT JOIN (Task 1 service + tests); quality summary track/category/dedup (Task 1); single look-back window on `collected_at` (Task 1); markdown + HTML via `core/report_html` + `--format`/`--days`/`--since`/`--until`/`--top`/`--save` (Task 3); empty-state markers (Tasks 2/3); docs (Task 4). Click rate explicitly excluded per spec non-goals. All design sections map to a task.
- **Type consistency:** `SourceStat`/`QualitySummary`/`DashboardReport` defined in Task 1 and consumed by service/report/cli. `build_dashboard(session, *, days, until, since, top_categories)` signature used identically in cli. `render_markdown(report)` and `render_report_html(md, *, title)` consistent. CLI param `fmt`/`--format` matches the established convention.
- **No placeholders:** every code step shows complete code; every run step has an exact command and expected outcome.
- **Determinism:** all metrics computed from seeded DB rows; no LLM, no external calls. `collected_at` is set explicitly in test seeds so window filtering is deterministic.
</content>
