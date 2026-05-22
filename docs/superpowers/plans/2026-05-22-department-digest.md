# Department Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `newsletter departments digest` report that, for each enabled department, selects the most relevant accumulated articles (embedding cosine, with keyword-overlap fallback) and renders them as markdown or HTML.

**Architecture:** Extend the existing `departments` slice with three new modules — `relevance.py` (pure scoring), `digest.py` (DB + embedding aggregation), `report.py` (pure markdown) — plus digest dataclasses in `schemas.py` and a `digest` subcommand in `cli.py`. Relevance mode is chosen per run: embedding cosine when an embedding client yields department vectors, else keyword overlap. No new tables, no sending, no LLM.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Typer, `markdown-it-py`, pytest. Reuses `core/embeddings`, `core/text`, `core/report_html`, `monitoring.recorder.build_embedding_client`.

---

## Design Source

Full design: `docs/superpowers/specs/2026-05-22-department-digest-design.md`. Brainstorming complete — do not re-brainstorm. Per-department sending/recipients is explicitly out of scope (spec §21 deferral).

## File Structure

| Kind | Path | Responsibility |
|---|---|---|
| Create | `src/newsletter/slices/departments/relevance.py` | pure: department tokens, keyword overlap, cosine wrapper |
| Create | `src/newsletter/slices/departments/digest.py` | DB+embedding: window query → per-department ranking → `DepartmentDigest` |
| Create | `src/newsletter/slices/departments/report.py` | pure: `DepartmentDigest` → markdown |
| Modify | `src/newsletter/slices/departments/schemas.py` | append `RelevantHeadline`, `DepartmentDigestEntry`, `DepartmentDigest` |
| Modify | `src/newsletter/slices/departments/cli.py` | add `digest` command |
| Modify | `AGENTS.md` | document the command |
| Create (tests) | `tests/slices/departments/{test_relevance,test_digest,test_digest_report,test_digest_cli}.py` | per-module tests |

---

### Task 1: relevance.py (pure scoring)

**Files:**
- Create: `src/newsletter/slices/departments/relevance.py`
- Test: `tests/slices/departments/test_relevance.py`

- [ ] **Step 1: Write the failing test**

Create `tests/slices/departments/test_relevance.py`:

```python
"""departments.relevance — pure scoring helpers."""

from __future__ import annotations

from newsletter.slices.departments.relevance import (
    department_tokens,
    embedding_score,
    keyword_score,
)


def test_department_tokens_drops_short_and_stopwords():
    toks = department_tokens("영업", "고객 매출 the a")
    assert "영업" in toks
    assert "고객" in toks
    assert "매출" in toks
    assert "the" not in toks  # stopword
    assert "a" not in toks  # length-1


def test_keyword_score_counts_overlap():
    dept = department_tokens("영업", "고객 매출 영업")
    assert keyword_score(dept, "신규 고객 매출 분석 발표") == 2  # 고객, 매출
    assert keyword_score(dept, "엔지니어링 코드 리뷰") == 0


def test_embedding_score_cosine_and_empty():
    assert embedding_score([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert embedding_score([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert embedding_score([], [1.0, 0.0]) == 0.0
    assert embedding_score([1.0, 0.0], []) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/slices/departments/test_relevance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.departments.relevance'`

- [ ] **Step 3: Write the implementation**

Create `src/newsletter/slices/departments/relevance.py`:

```python
"""Pure relevance scoring for the department digest (no IO).

Two modes, chosen per run by the caller: embedding cosine when both the
department and the item carry vectors, else keyword overlap on tokens.
"""

from __future__ import annotations

from collections.abc import Sequence

from newsletter.core.embeddings import cosine
from newsletter.core.text import tokenize


def department_tokens(name: str, description: str | None) -> set[str]:
    """Lowercased token set for a department (name + description)."""
    return set(tokenize(f"{name} {description or ''}"))


def keyword_score(dept_tokens: set[str], item_text: str) -> int:
    """Count of distinct department tokens present in the item's tokens."""
    return len(dept_tokens & set(tokenize(item_text)))


def embedding_score(dept_vec: Sequence[float], item_vec: Sequence[float]) -> float:
    """Cosine similarity; 0.0 when either vector is empty."""
    if not dept_vec or not item_vec:
        return 0.0
    return cosine(dept_vec, item_vec)


__all__ = ["department_tokens", "embedding_score", "keyword_score"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/slices/departments/test_relevance.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/departments/relevance.py tests/slices/departments/test_relevance.py
uv run ruff format src/newsletter/slices/departments/relevance.py tests/slices/departments/test_relevance.py
git add src/newsletter/slices/departments/relevance.py tests/slices/departments/test_relevance.py
git commit -m "feat(departments): pure relevance scoring for digest"
```

---

### Task 2: schemas + digest.py service

**Files:**
- Modify: `src/newsletter/slices/departments/schemas.py`
- Create: `src/newsletter/slices/departments/digest.py`
- Test: `tests/slices/departments/test_digest.py`

- [ ] **Step 1: Append digest dataclasses to schemas.py**

Add to the end of `src/newsletter/slices/departments/schemas.py` (the file currently has only the Pydantic registry models and imports `datetime`; add the new imports at the top and the dataclasses at the bottom):

At the top, after `from datetime import datetime`, add:
```python
from dataclasses import dataclass
from datetime import date
```

At the bottom of the file, append:
```python
@dataclass(frozen=True, slots=True)
class RelevantHeadline:
    title: str
    url: str
    score: float


@dataclass(frozen=True, slots=True)
class DepartmentDigestEntry:
    name: str
    headlines: list[RelevantHeadline]  # score desc, top_k


@dataclass(frozen=True, slots=True)
class DepartmentDigest:
    since: date
    until: date  # exclusive
    total_items: int  # items scanned in window
    mode: str  # "embedding" | "keyword"
    departments: list[DepartmentDigestEntry]  # enabled departments, by id
```

- [ ] **Step 2: Write the failing digest test**

Create `tests/slices/departments/test_digest.py`:

```python
"""departments.digest — per-department ranking over a window."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy.orm import Session

from newsletter.core.embeddings import DisabledEmbeddingClient, serialize
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.departments import repository
from newsletter.slices.departments.digest import build_department_digest
from newsletter.slices.departments.schemas import DepartmentCreate
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

_UNTIL = date(2026, 5, 22)


class _FakeEmbed:
    """Returns the given vectors in order, one per input text."""

    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = vectors

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self._vectors[: len(texts)]


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
    summary: str,
    published_at: datetime,
    embedding: bytes | None = None,
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
            importance_score=1.0,
            summary=summary,
            keywords=None,
            duplicate_group_id=None,
            embedding=embedding,
        )
    )
    db_session.flush()


def test_keyword_mode_ranks_by_overlap(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, DepartmentCreate(name="영업", description="고객 매출 영업"))
    repository.add(db_session, DepartmentCreate(name="기술", description="엔지니어링 코드 개발"))
    _seed_item(db_session, title="신규 고객 매출 분석", summary="영업 성과", published_at=datetime(2026, 5, 20, 9, 0))
    _seed_item(db_session, title="코드 리뷰 개발 도구", summary="엔지니어링 생산성", published_at=datetime(2026, 5, 20, 10, 0))
    db_session.commit()

    digest = build_department_digest(
        db_session, days=7, until=_UNTIL, embed_client=DisabledEmbeddingClient()
    )
    assert digest.mode == "keyword"
    by_name = {e.name: e for e in digest.departments}
    assert by_name["영업"].headlines[0].title == "신규 고객 매출 분석"
    assert by_name["기술"].headlines[0].title == "코드 리뷰 개발 도구"


def test_embedding_mode_ranks_by_cosine(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, DepartmentCreate(name="A", description="alpha"))
    _seed_item(
        db_session, title="aligned", summary="x", published_at=datetime(2026, 5, 20, 9, 0),
        embedding=serialize([1.0, 0.0]),
    )
    _seed_item(
        db_session, title="orthogonal", summary="y", published_at=datetime(2026, 5, 20, 10, 0),
        embedding=serialize([0.0, 1.0]),
    )
    db_session.commit()

    digest = build_department_digest(
        db_session, days=7, until=_UNTIL, embed_client=_FakeEmbed([[1.0, 0.0]])
    )
    assert digest.mode == "embedding"
    headlines = digest.departments[0].headlines
    assert [h.title for h in headlines] == ["aligned"]  # orthogonal scores 0 -> excluded


def test_window_filtering(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, DepartmentCreate(name="영업", description="고객"))
    _seed_item(db_session, title="고객 인", summary="x", published_at=datetime(2026, 5, 20, 9, 0))
    _seed_item(db_session, title="고객 아웃", summary="x", published_at=datetime(2026, 4, 1, 9, 0))
    db_session.commit()
    digest = build_department_digest(
        db_session, days=7, until=_UNTIL, embed_client=DisabledEmbeddingClient()
    )
    assert digest.total_items == 1
    assert digest.departments[0].headlines[0].title == "고객 인"


def test_top_k_truncation_and_zero_excluded(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, DepartmentCreate(name="영업", description="고객"))
    for i in range(3):
        _seed_item(db_session, title=f"고객 사례 {i}", summary="x", published_at=datetime(2026, 5, 20, 9, i))
    _seed_item(db_session, title="무관한 기사", summary="배포 파이프라인", published_at=datetime(2026, 5, 20, 9, 30))
    db_session.commit()
    digest = build_department_digest(
        db_session, days=7, until=_UNTIL, top_k=2, embed_client=DisabledEmbeddingClient()
    )
    headlines = digest.departments[0].headlines
    assert len(headlines) == 2  # truncated; the unrelated article (score 0) excluded
    assert all("고객" in h.title for h in headlines)


def test_empty_departments(db_session: Session):
    _seed_source(db_session)
    _seed_item(db_session, title="고객", summary="x", published_at=datetime(2026, 5, 20, 9, 0))
    db_session.commit()
    digest = build_department_digest(
        db_session, days=7, until=_UNTIL, embed_client=DisabledEmbeddingClient()
    )
    assert digest.departments == []
    assert digest.mode == "keyword"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/slices/departments/test_digest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.departments.digest'`

- [ ] **Step 4: Write digest.py**

Create `src/newsletter/slices/departments/digest.py`:

```python
"""Department digest: per-department most-relevant items over a window.

Embedding mode (cosine) when the embedding client yields department vectors,
else keyword-overlap fallback. Read-only; no sending. Window/anchor philosophy
mirrors trends/competitors (published_at, else created_at, naive UTC).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from newsletter.core.embeddings import EmbeddingClient, deserialize
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.departments import repository
from newsletter.slices.departments.relevance import (
    department_tokens,
    embedding_score,
    keyword_score,
)
from newsletter.slices.departments.schemas import (
    DepartmentDigest,
    DepartmentDigestEntry,
    RelevantHeadline,
)


def build_department_digest(
    session: Session,
    *,
    days: int = 7,
    until: date | None = None,
    since: date | None = None,
    top_k: int = 5,
    embed_client: EmbeddingClient,
) -> DepartmentDigest:
    """Per-department top-relevant items for one look-back window."""
    until_date = until or (date.today() + timedelta(days=1))
    since_date = since or (until_date - timedelta(days=days))
    lo = datetime.combine(since_date, time.min)
    hi = datetime.combine(until_date, time.min)

    depts = repository.list_departments(session, only_enabled=True)
    dept_texts = [f"{d.name} {d.description or ''}" for d in depts]
    dept_vectors = embed_client.embed(dept_texts) if depts else []
    embedding_mode = bool(depts) and len(dept_vectors) == len(depts) and any(dept_vectors)
    mode = "embedding" if embedding_mode else "keyword"

    dept_tok = [department_tokens(d.name, d.description) for d in depts]

    items: list[tuple[str, str, str, list[float]]] = []
    total_items = 0
    for title, url, summary, emb, published_at, created_at in _fetch(session, lo, hi):
        anchor = _anchor(published_at, created_at)
        if anchor is None or not (lo <= anchor < hi):
            continue
        total_items += 1
        items.append((title, url, f"{title or ''} {summary or ''}", deserialize(emb)))

    entries: list[DepartmentDigestEntry] = []
    for idx, _dept in enumerate(depts):
        scored: list[RelevantHeadline] = []
        for title, url, text, vec in items:
            if embedding_mode:
                score = embedding_score(dept_vectors[idx], vec)
            else:
                score = float(keyword_score(dept_tok[idx], text))
            if score > 0:
                scored.append(RelevantHeadline(title=title, url=url, score=score))
        scored.sort(key=lambda h: h.score, reverse=True)
        entries.append(DepartmentDigestEntry(name=_dept.name, headlines=scored[:top_k]))

    return DepartmentDigest(
        since=since_date,
        until=until_date,
        total_items=total_items,
        mode=mode,
        departments=entries,
    )


def _fetch(session: Session, lo: datetime, hi: datetime):
    """Rows whose anchor (published_at, else created_at) falls in [lo, hi)."""
    stmt = (
        select(
            ProcessedItem.normalized_title,
            ProcessedItem.canonical_url,
            ProcessedItem.summary,
            ProcessedItem.embedding,
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


__all__ = ["build_department_digest"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/slices/departments/test_digest.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/departments tests/slices/departments
uv run ruff format src/newsletter/slices/departments tests/slices/departments
git add src/newsletter/slices/departments tests/slices/departments
git commit -m "feat(departments): per-department digest aggregation service"
```

---

### Task 3: report.py

**Files:**
- Create: `src/newsletter/slices/departments/report.py`
- Test: `tests/slices/departments/test_digest_report.py`

- [ ] **Step 1: Write the failing report test**

Create `tests/slices/departments/test_digest_report.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/slices/departments/test_digest_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.departments.report'`

- [ ] **Step 3: Write report.py**

Create `src/newsletter/slices/departments/report.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/slices/departments/test_digest_report.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/departments tests/slices/departments
uv run ruff format src/newsletter/slices/departments tests/slices/departments
git add src/newsletter/slices/departments tests/slices/departments
git commit -m "feat(departments): markdown rendering for digest"
```

---

### Task 4: cli.py `digest` command

**Files:**
- Modify: `src/newsletter/slices/departments/cli.py`
- Test: `tests/slices/departments/test_digest_cli.py`

- [ ] **Step 1: Write the failing CLI test**

Create `tests/slices/departments/test_digest_cli.py`:

```python
"""departments digest CLI smoke tests. No VOYAGE key in tests, so the digest
runs in keyword mode — output is deterministic."""

from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.departments import repository
from newsletter.slices.departments.cli import app
from newsletter.slices.departments.schemas import DepartmentCreate
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
    repository.add(db_session, DepartmentCreate(name="영업", description="고객 매출"))
    raw = RawItem(
        source_id="src",
        title="고객 매출 분석",
        url="https://example.com/x",
        published_at=datetime(2026, 5, 20, 9, 0),
        raw_summary="영업 성과",
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title="고객 매출 분석",
            canonical_url="https://example.com/x",
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=1.0,
            summary="영업 성과",
        )
    )
    db_session.commit()


def test_digest_smoke(db_session):
    _seed(db_session)
    result = runner.invoke(app, ["digest", "--since", "2026-05-15", "--until", "2026-05-22"])
    assert result.exit_code == 0, result.output
    assert "부서별 다이제스트" in result.output
    assert "영업" in result.output
    assert "고객 매출 분석" in result.output


def test_digest_html_format(db_session):
    _seed(db_session)
    result = runner.invoke(
        app, ["digest", "--since", "2026-05-15", "--until", "2026-05-22", "--format", "html"]
    )
    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("<!DOCTYPE html>")
    assert "부서별 다이제스트" in result.output


def test_digest_save_to_file(tmp_path, db_session):
    _seed(db_session)
    out = tmp_path / "dept.md"
    result = runner.invoke(
        app, ["digest", "--since", "2026-05-15", "--until", "2026-05-22", "--save", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "부서별 다이제스트" in out.read_text(encoding="utf-8")


def test_digest_rejects_bad_format(db_session):
    result = runner.invoke(app, ["digest", "--format", "pdf"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/slices/departments/test_digest_cli.py -v`
Expected: FAIL — `No such command 'digest'` (the command does not exist yet) → non-zero exit.

- [ ] **Step 3: Add the `digest` command to cli.py**

In `src/newsletter/slices/departments/cli.py`, add these imports after the existing import block (after `from newsletter.slices.departments.seeds import seed as seed_departments`):

```python
from datetime import date as date_cls
from pathlib import Path

from newsletter.core.report_html import render_report_html
from newsletter.slices.departments.digest import build_department_digest
from newsletter.slices.departments.report import render_markdown
from newsletter.slices.monitoring.recorder import build_embedding_client
```

Append this command to the end of the file:

```python
@app.command("digest")
def cmd_digest(
    days: int = typer.Option(7, "--days", help="Look-back window length in days."),
    since: str | None = typer.Option(
        None, "--since", help="Window start YYYY-MM-DD (wins over --days)."
    ),
    until: str | None = typer.Option(
        None, "--until", help="Exclusive window end YYYY-MM-DD (default tomorrow)."
    ),
    top: int = typer.Option(5, "--top", help="Max headlines per department."),
    fmt: str = typer.Option("md", "--format", help="md or html."),
    save: str | None = typer.Option(
        None, "--save", help="Write the report to this path instead of stdout."
    ),
) -> None:
    """Per-department most-relevant articles (embedding match, keyword fallback)."""
    if fmt not in ("md", "html"):
        typer.echo("format must be 'md' or 'html'", err=True)
        raise typer.Exit(code=1)
    since_date = date_cls.fromisoformat(since) if since else None
    until_date = date_cls.fromisoformat(until) if until else None
    with session_scope() as session:
        digest = build_department_digest(
            session,
            days=days,
            until=until_date,
            since=since_date,
            top_k=top,
            embed_client=build_embedding_client(),
        )

    markdown = render_markdown(digest)
    output = (
        render_report_html(markdown, title="부서별 다이제스트")
        if fmt == "html"
        else markdown
    )
    if save:
        Path(save).write_text(output, encoding="utf-8")
        typer.echo(f"부서별 다이제스트 저장: {save}")
    else:
        typer.echo(output)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/slices/departments/test_digest_cli.py -v`
Expected: PASS (4 passed). The existing `tests/slices/departments/test_cli.py` (registry commands) must still pass too.

- [ ] **Step 5: Verify the command appears**

Run: `uv run newsletter departments --help`
Expected: command list now includes `digest` alongside `list/add/disable/enable/remove/seed`.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/departments tests/slices/departments
uv run ruff format src/newsletter/slices/departments tests/slices/departments
git add src/newsletter/slices/departments tests/slices/departments
git commit -m "feat(departments): digest CLI command"
```

---

### Task 5: AGENTS.md docs + full verification

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update the departments command row**

Edit `AGENTS.md`. Find the row documenting `newsletter departments` (registry CRUD). Add a dedicated row for the digest right after it:

```markdown
| `uv run newsletter departments digest [--days N \| --since DATE] [--until DATE] [--top K] [--format md\|html] [--save PATH]` | Per-department most-relevant articles (embedding match, keyword fallback) |
```

(If there is no existing `departments` row in the command table, add both: keep the existing registry behavior described in the slice tree, and add the digest row above.)

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -q`
Expected: all pass. Prior baseline was 626; this adds ~15 (3 relevance + 5 digest + 3 report + 4 cli), so expect ~641 passing, 0 failed.

- [ ] **Step 3: Manual smoke**

Run: `uv run newsletter departments seed` then `uv run newsletter departments digest --days 3650`
Expected: prints `# 부서별 다이제스트` with a `- 관련도: 키워드` line (no VOYAGE key locally) and a `## {dept}` section per seeded department (each likely `(관련 기사 없음)` against an empty dev DB — that's fine).

- [ ] **Step 4: Lint check**

Run: `uv run ruff check src/newsletter/slices/departments tests/slices/departments`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md
git commit -m "docs(departments): document the digest command"
```

---

## Self-Review Notes

- **Spec coverage:** pure relevance (Task 1); per-department window aggregation with embedding/keyword mode selection (Task 2); markdown render with mode + empty markers (Task 3); `digest` CLI + HTML + format/window flags (Task 4); docs (Task 5). Embedding department vectors are computed on the fly (no migration). Sending/recipients explicitly excluded. All design sections map to a task.
- **Type consistency:** `RelevantHeadline`/`DepartmentDigestEntry`/`DepartmentDigest` defined in Task 2 (schemas) and consumed by digest/report/cli. `build_department_digest(session, *, days, until, since, top_k, embed_client)` signature is used identically in cli and tests. `department_tokens`/`keyword_score`/`embedding_score` from Task 1 are consumed by Task 2. CLI param `fmt`/`--format` matches the established convention.
- **No placeholders:** every code step shows complete code; every run step has an exact command and expected outcome.
- **Determinism:** the test environment has no VOYAGE key, so `build_embedding_client()` yields `DisabledEmbeddingClient` → `embed()` returns `[]` → keyword mode → deterministic CLI output. Embedding mode is exercised with an injected `_FakeEmbed` returning fixed vectors against seeded `serialize(...)` embeddings.
</content>
