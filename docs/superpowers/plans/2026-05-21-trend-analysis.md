# 트렌드 분석 (trends 슬라이스) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 누적 ProcessedItem의 제목 키워드를 두 기간(현재 vs 직전)으로 집계해 떠오르는/식는/신규/소멸 용어를 보여주는 독립 트렌드 리포트(CLI + 마크다운)를 만든다.

**Architecture:** 토큰화를 `core/text.py`로 추출해 corpus와 공유한다. 새 `trends` 슬라이스(terms·analysis·service·report·cli)는 순수 함수(토큰화·비교·렌더)와 DB 조회(두 윈도우)를 분리한다. 새 테이블·영속화 없이 누적 데이터에서 매번 재계산한다.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Typer, pytest. LLM/임베딩 미사용.

**설계 문서:** `docs/superpowers/specs/2026-05-21-trend-analysis-design.md`

---

## File Structure

| 파일 | 책임 |
|---|---|
| `src/newsletter/core/text.py` (생성) | 공유 `tokenize()` + `STOPWORDS` |
| `src/newsletter/slices/corpus/chunking.py` (수정) | `extract_keywords`가 `core.text.tokenize` 사용 |
| `src/newsletter/slices/trends/terms.py` (생성) | `title_terms(title) -> set[str]` |
| `src/newsletter/slices/trends/schemas.py` (생성) | `WindowSpec`, `TermDelta`, `TrendBuckets`, `TrendReport` |
| `src/newsletter/slices/trends/analysis.py` (생성) | `compare_windows(...) -> TrendBuckets` |
| `src/newsletter/slices/trends/service.py` (생성) | `build_window_spec`, `analyze_trends` (DB) |
| `src/newsletter/slices/trends/report.py` (생성) | `render_markdown(report) -> str` |
| `src/newsletter/slices/trends/cli.py` (생성) | `newsletter trends` |
| `src/newsletter/slices/trends/__init__.py` (생성) | 빈 패키지 마커 |
| `src/newsletter/cli.py` (수정) | `trends_app` 루트 등록 |
| `AGENTS.md` (수정) | 문서 |

테스트는 `tests/slices/trends/`(신규)와 `tests/core/`(신규 또는 기존)에 둔다.

---

## Task 1: core/text.py 추출 + corpus/chunking 리팩터

**Files:**
- Create: `src/newsletter/core/text.py`
- Modify: `src/newsletter/slices/corpus/chunking.py`
- Test: `tests/core/__init__.py`, `tests/core/test_text.py`

- [ ] **Step 1: 빈 테스트 패키지 마커 생성 (없으면)**

`tests/core/__init__.py` 를 빈 파일로 생성한다(이미 있으면 건너뛴다).

```python
```

- [ ] **Step 2: 실패 테스트 작성 — `tests/core/test_text.py`**

```python
"""core.text — shared lowercased word tokenization."""

from __future__ import annotations

from newsletter.core.text import STOPWORDS, tokenize


def test_tokenize_lowercases_and_splits():
    assert tokenize("OpenAI GPT Model") == ["openai", "gpt", "model"]


def test_tokenize_drops_single_char_and_stopwords():
    out = tokenize("the a AI 및 모델 x")
    assert "the" not in out
    assert "및" not in out  # stopword
    assert "x" not in out   # length 1
    assert "ai" in out
    assert "모델" in out


def test_tokenize_keeps_korean_and_digits():
    out = tokenize("GPT5 출시 2026")
    assert "gpt5" in out
    assert "출시" in out
    assert "2026" in out


def test_stopwords_is_frozenset():
    assert isinstance(STOPWORDS, frozenset)
    assert "the" in STOPWORDS
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `uv run pytest tests/core/test_text.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.core.text`

- [ ] **Step 4: `src/newsletter/core/text.py` 구현**

```python
"""Shared lowercased word tokenization used by the corpus + trends slices.

Pure, deterministic, no IO. Lowercases input, extracts word tokens, and drops
length-1 tokens and a light stopword set.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[0-9a-z가-힣]+")

# Light stopword set — common English glue words + Korean particles/fillers.
# Single-character tokens are dropped separately, so only len>1 entries matter.
STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "but", "not", "you", "with", "this",
        "that", "from", "have", "was", "were", "한다", "합니다", "있다",
        "있습니다", "그리고", "그러나", "또는", "등의", "대한", "위한",
    }
)


def tokenize(text: str) -> list[str]:
    """Lowercased word tokens, dropping length-1 tokens and stopwords."""
    return [
        t
        for t in _TOKEN_RE.findall(text.lower())
        if len(t) > 1 and t not in STOPWORDS
    ]


__all__ = ["STOPWORDS", "tokenize"]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/core/test_text.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: corpus/chunking.py 리팩터 (동작 보존)**

`src/newsletter/slices/corpus/chunking.py` 에서:
- 모듈 상단의 `_TOKEN_RE = re.compile(r"[0-9a-z가-힣]+")` 줄과 `_STOPWORDS = frozenset({...})` 블록(주석 포함)을 삭제한다. (`_HEADING_LINE_RE` 는 그대로 둔다. `import re` 도 그대로 — heading regex가 쓴다.)
- `from collections import Counter` 아래에 import 추가:
```python
from newsletter.core.text import tokenize
```
- `extract_keywords` 를 다음으로 교체:
```python
def extract_keywords(text: str, *, max_keywords: int = 20) -> list[str]:
    """Frequency-ranked lowercased tokens. Deterministic (alpha tie-break)."""
    counts = Counter(tokenize(text))
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [token for token, _ in ranked[:max_keywords]]
```

- [ ] **Step 7: corpus 회귀 + core 테스트 확인**

Run: `uv run pytest tests/slices/corpus/test_chunking.py tests/core/test_text.py -v`
Expected: PASS (기존 chunking 8개 + core 4개 = 12 passed). 회귀 없음.

- [ ] **Step 8: ruff**

Run: `uv run ruff check src/newsletter/core/text.py src/newsletter/slices/corpus/chunking.py tests/core/test_text.py`
Expected: clean (필요 시 `--fix`).

- [ ] **Step 9: 커밋**

```bash
git add src/newsletter/core/text.py src/newsletter/slices/corpus/chunking.py tests/core/
git commit -m "refactor(core): extract shared tokenize() into core/text; reuse in corpus"
```

---

## Task 2: trends/terms.py

**Files:**
- Create: `src/newsletter/slices/trends/__init__.py` (empty)
- Create: `src/newsletter/slices/trends/terms.py`
- Test: `tests/slices/trends/__init__.py` (empty), `tests/slices/trends/test_terms.py`

- [ ] **Step 1: 빈 패키지 마커 생성**

`src/newsletter/slices/trends/__init__.py` 와 `tests/slices/trends/__init__.py` 를 빈 파일로 생성한다.

```python
```

- [ ] **Step 2: 실패 테스트 작성 — `tests/slices/trends/test_terms.py`**

```python
"""trends.terms — per-title distinct terms."""

from __future__ import annotations

from newsletter.slices.trends.terms import title_terms


def test_title_terms_dedupes_within_title():
    # "rag" appears twice -> counted once per title
    assert title_terms("RAG agent RAG pipeline") == {"rag", "agent", "pipeline"}


def test_title_terms_empty_title():
    assert title_terms("") == set()


def test_title_terms_drops_stopwords_and_short():
    assert "the" not in title_terms("The AI model")
    assert "ai" in title_terms("The AI model")
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `uv run pytest tests/slices/trends/test_terms.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.slices.trends.terms`

- [ ] **Step 4: `src/newsletter/slices/trends/terms.py` 구현**

```python
"""Pure title → distinct-terms mapping for trend analysis."""

from __future__ import annotations

from newsletter.core.text import tokenize


def title_terms(title: str) -> set[str]:
    """Distinct terms in one title (per-article dedup)."""
    return set(tokenize(title))


__all__ = ["title_terms"]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/slices/trends/test_terms.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 커밋**

```bash
git add src/newsletter/slices/trends/__init__.py src/newsletter/slices/trends/terms.py tests/slices/trends/
git commit -m "feat(trends): title_terms tokenization"
```

---

## Task 3: trends/schemas.py + trends/analysis.py

**Files:**
- Create: `src/newsletter/slices/trends/schemas.py`
- Create: `src/newsletter/slices/trends/analysis.py`
- Test: `tests/slices/trends/test_analysis.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/slices/trends/test_analysis.py`**

```python
"""trends.analysis — classify terms into trend buckets."""

from __future__ import annotations

from newsletter.slices.trends.analysis import compare_windows


def _imp(terms):
    return {t: 0.0 for t in terms}


def test_new_terms_appear_with_min_count():
    cur = {"sora": 3}
    prev = {}
    buckets = compare_windows(cur, prev, importance=_imp(cur))
    assert [d.term for d in buckets.new] == ["sora"]
    assert buckets.rising == []


def test_below_min_count_is_excluded():
    cur = {"sora": 1}  # below default min_count=2
    prev = {}
    buckets = compare_windows(cur, prev, importance=_imp(cur))
    assert buckets.new == []


def test_dropped_terms():
    cur = {}
    prev = {"clubhouse": 4}
    buckets = compare_windows(cur, prev, importance={})
    assert [d.term for d in buckets.dropped] == ["clubhouse"]


def test_rising_and_fading():
    cur = {"rag": 8, "nft": 2}
    prev = {"rag": 3, "nft": 6}
    buckets = compare_windows(cur, prev, importance=_imp(cur))
    assert [d.term for d in buckets.rising] == ["rag"]
    assert [d.term for d in buckets.fading] == ["nft"]
    rag = buckets.rising[0]
    assert rag.current == 8 and rag.previous == 3 and rag.delta == 5


def test_top_n_truncation():
    cur = {f"t{i}": 5 for i in range(20)}
    prev = {}
    buckets = compare_windows(cur, prev, importance=_imp(cur), top_n=3)
    assert len(buckets.new) == 3


def test_importance_breaks_ties_in_top_current():
    cur = {"a": 5, "b": 5}
    prev = {}
    buckets = compare_windows(cur, prev, importance={"a": 1.0, "b": 9.0})
    # equal counts -> higher importance first
    assert [d.term for d in buckets.top_current] == ["b", "a"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/slices/trends/test_analysis.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.slices.trends.analysis`

- [ ] **Step 3: `src/newsletter/slices/trends/schemas.py` 구현**

```python
"""Output shapes for trend analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class WindowSpec:
    period: str          # "week" | "month"
    current_start: date
    current_end: date    # exclusive
    previous_start: date
    previous_end: date   # exclusive (== current_start)


@dataclass(frozen=True, slots=True)
class TermDelta:
    term: str
    current: int         # article count this window
    previous: int        # article count prior window
    delta: int           # current - previous
    importance: float    # sum of importance_score this window (tiebreak)


@dataclass(frozen=True, slots=True)
class TrendBuckets:
    rising: list[TermDelta]
    fading: list[TermDelta]
    new: list[TermDelta]
    dropped: list[TermDelta]
    top_current: list[TermDelta]


@dataclass(frozen=True, slots=True)
class TrendReport:
    window: WindowSpec
    rising: list[TermDelta]
    fading: list[TermDelta]
    new: list[TermDelta]
    dropped: list[TermDelta]
    top_current: list[TermDelta]
    total_current_items: int
    total_previous_items: int


__all__ = ["TermDelta", "TrendBuckets", "TrendReport", "WindowSpec"]
```

- [ ] **Step 4: `src/newsletter/slices/trends/analysis.py` 구현**

```python
"""Pure trend classification: compare two term-frequency windows."""

from __future__ import annotations

from newsletter.slices.trends.schemas import TermDelta, TrendBuckets


def compare_windows(
    current: dict[str, int],
    previous: dict[str, int],
    *,
    importance: dict[str, float],
    top_n: int = 15,
    min_count: int = 2,
) -> TrendBuckets:
    """Classify terms into rising/fading/new/dropped/top_current buckets.

    ``current``/``previous`` map term -> article count. ``importance`` maps
    term -> summed importance_score this window (used only as a tiebreak).
    Terms below ``min_count`` in the relevant window are dropped as noise.
    Each bucket is truncated to ``top_n``.
    """
    rising: list[TermDelta] = []
    fading: list[TermDelta] = []
    new: list[TermDelta] = []
    dropped: list[TermDelta] = []

    for term in set(current) | set(previous):
        c = current.get(term, 0)
        p = previous.get(term, 0)
        delta = TermDelta(
            term=term, current=c, previous=p, delta=c - p,
            importance=importance.get(term, 0.0),
        )
        if p == 0 and c >= min_count:
            new.append(delta)
        elif c == 0 and p >= min_count:
            dropped.append(delta)
        elif c > p > 0 and c >= min_count:
            rising.append(delta)
        elif 0 < c < p and p >= min_count:
            fading.append(delta)

    rising.sort(key=lambda d: (-d.delta, -d.importance, d.term))
    new.sort(key=lambda d: (-d.current, -d.importance, d.term))
    fading.sort(key=lambda d: (d.delta, -d.importance, d.term))
    dropped.sort(key=lambda d: (-d.previous, d.term))

    top_current = sorted(
        (
            TermDelta(
                term=term, current=c, previous=previous.get(term, 0),
                delta=c - previous.get(term, 0),
                importance=importance.get(term, 0.0),
            )
            for term, c in current.items()
            if c >= min_count
        ),
        key=lambda d: (-d.current, -d.importance, d.term),
    )

    return TrendBuckets(
        rising=rising[:top_n],
        fading=fading[:top_n],
        new=new[:top_n],
        dropped=dropped[:top_n],
        top_current=top_current[:top_n],
    )


__all__ = ["compare_windows"]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/slices/trends/test_analysis.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: 커밋**

```bash
git add src/newsletter/slices/trends/schemas.py src/newsletter/slices/trends/analysis.py tests/slices/trends/test_analysis.py
git commit -m "feat(trends): window comparison + trend buckets"
```

---

## Task 4: trends/service.py (DB 조회 + 윈도우)

**Files:**
- Create: `src/newsletter/slices/trends/service.py`
- Test: `tests/slices/trends/test_service.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/slices/trends/test_service.py`**

```python
"""trends.service — window math + DB aggregation."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate
from newsletter.slices.trends.service import analyze_trends, build_window_spec

_END = date(2026, 5, 21)


def test_build_window_spec_week():
    spec = build_window_spec("week", _END)
    # current covers the 7 days ending on _END inclusive -> [05-15, 05-22)
    assert spec.current_start == date(2026, 5, 15)
    assert spec.current_end == date(2026, 5, 22)
    assert spec.previous_start == date(2026, 5, 8)
    assert spec.previous_end == date(2026, 5, 15)


def test_build_window_spec_rejects_bad_period():
    import pytest

    with pytest.raises(ValueError):
        build_window_spec("yearly", _END)


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


def _seed(
    db_session: Session,
    *,
    title: str,
    published_at: datetime | None,
    created_at: datetime | None = None,
) -> None:
    raw = RawItem(
        source_id="src",
        title=title,
        url=f"https://example.com/{title[:24]}-{published_at}",
        published_at=published_at,
        raw_summary=title,
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    kwargs = {}
    if created_at is not None:
        kwargs["created_at"] = created_at
    proc = ProcessedItem(
        raw_item_id=raw.id,
        normalized_title=title,
        canonical_url=raw.url,
        content_track="expert_news",
        category="AI Model",
        relevance_score=0.9,
        importance_score=1.0,
        summary=title,
        keywords=None,
        duplicate_group_id=None,
        **kwargs,
    )
    db_session.add(proc)
    db_session.flush()


def test_analyze_splits_current_and_previous(db_session: Session):
    _seed_source(db_session)
    # current window item (in [05-15, 05-22))
    _seed(db_session, title="Sora video model", published_at=datetime(2026, 5, 18, 9, 0))
    # previous window item (in [05-08, 05-15))
    _seed(db_session, title="Clubhouse audio app", published_at=datetime(2026, 5, 10, 9, 0))
    db_session.commit()

    report = analyze_trends(db_session, period="week", end=_END, min_count=1)
    assert report.total_current_items == 1
    assert report.total_previous_items == 1
    new_terms = {d.term for d in report.new}
    dropped_terms = {d.term for d in report.dropped}
    assert "sora" in new_terms
    assert "clubhouse" in dropped_terms


def test_analyze_falls_back_to_created_at_when_published_is_null(db_session: Session):
    _seed_source(db_session)
    _seed(
        db_session,
        title="Fallback topic here",
        published_at=None,
        created_at=datetime(2026, 5, 18, 9, 0),  # current window
    )
    db_session.commit()
    report = analyze_trends(db_session, period="week", end=_END, min_count=1)
    assert report.total_current_items == 1
    assert "fallback" in {d.term for d in report.new}


def test_analyze_empty_window(db_session: Session):
    report = analyze_trends(db_session, period="week", end=_END)
    assert report.total_current_items == 0
    assert report.total_previous_items == 0
    assert report.new == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/slices/trends/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.slices.trends.service`

- [ ] **Step 3: `src/newsletter/slices/trends/service.py` 구현**

```python
"""Trend analysis over accumulated ProcessedItem rows.

The service is the only place that touches the DB. It resolves two equal-length
date windows (current vs previous), anchoring each item by published_at (falling
back to created_at), counts distinct title terms per article, and delegates the
classification to the pure ``compare_windows``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.trends.analysis import compare_windows
from newsletter.slices.trends.schemas import TrendReport, WindowSpec
from newsletter.slices.trends.terms import title_terms

_PERIOD_DAYS = {"week": 7, "month": 30}


def build_window_spec(period: str, end: date) -> WindowSpec:
    """Two equal-length windows ending on ``end`` (inclusive of end's date)."""
    if period not in _PERIOD_DAYS:
        raise ValueError(f"unknown period: {period!r} (expected week|month)")
    delta = timedelta(days=_PERIOD_DAYS[period])
    current_end = end + timedelta(days=1)  # exclusive upper bound
    current_start = current_end - delta
    previous_start = current_start - delta
    return WindowSpec(
        period=period,
        current_start=current_start,
        current_end=current_end,
        previous_start=previous_start,
        previous_end=current_start,
    )


def analyze_trends(
    session: Session,
    *,
    period: str = "week",
    end: date | None = None,
    top_n: int = 15,
    min_count: int = 2,
) -> TrendReport:
    """Build a TrendReport comparing the current window against the previous."""
    spec = build_window_spec(period, end or date.today())
    cur_lo = datetime.combine(spec.current_start, time.min)
    cur_hi = datetime.combine(spec.current_end, time.min)
    prev_lo = datetime.combine(spec.previous_start, time.min)

    current_counts: dict[str, int] = {}
    previous_counts: dict[str, int] = {}
    current_importance: dict[str, float] = {}
    total_current = 0
    total_previous = 0

    for title, importance, published_at, created_at in _fetch(session, prev_lo, cur_hi):
        anchor = _anchor(published_at, created_at)
        if anchor is None:
            continue
        if cur_lo <= anchor < cur_hi:
            total_current += 1
            for term in title_terms(title):
                current_counts[term] = current_counts.get(term, 0) + 1
                current_importance[term] = current_importance.get(term, 0.0) + (
                    importance or 0.0
                )
        elif prev_lo <= anchor < cur_lo:
            total_previous += 1
            for term in title_terms(title):
                previous_counts[term] = previous_counts.get(term, 0) + 1

    buckets = compare_windows(
        current_counts,
        previous_counts,
        importance=current_importance,
        top_n=top_n,
        min_count=min_count,
    )
    return TrendReport(
        window=spec,
        rising=buckets.rising,
        fading=buckets.fading,
        new=buckets.new,
        dropped=buckets.dropped,
        top_current=buckets.top_current,
        total_current_items=total_current,
        total_previous_items=total_previous,
    )


def _fetch(session: Session, lo: datetime, hi: datetime):
    """Rows whose anchor (published_at, else created_at) falls in [lo, hi)."""
    stmt = (
        select(
            ProcessedItem.normalized_title,
            ProcessedItem.importance_score,
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
    """Pick published_at else created_at, normalized to naive UTC for comparison."""
    dt = published_at if published_at is not None else created_at
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


__all__ = ["analyze_trends", "build_window_spec"]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/slices/trends/test_service.py -v`
Expected: PASS (5 passed)

Note: `RawItem.source_id` is NOT NULL, so `_seed_source` inserts a `Source` (source_id="src") once per DB test before items are seeded — mirrors `tests/slices/integration/test_service_interests.py`.

- [ ] **Step 5: ruff + 커밋**

Run: `uv run ruff check src/newsletter/slices/trends/service.py tests/slices/trends/test_service.py` → clean.

```bash
git add src/newsletter/slices/trends/service.py tests/slices/trends/test_service.py
git commit -m "feat(trends): window math + DB term aggregation"
```

---

## Task 5: trends/report.py (마크다운 렌더)

**Files:**
- Create: `src/newsletter/slices/trends/report.py`
- Test: `tests/slices/trends/test_report.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/slices/trends/test_report.py`**

```python
"""trends.report — deterministic markdown rendering."""

from __future__ import annotations

from datetime import date

from newsletter.slices.trends.report import render_markdown
from newsletter.slices.trends.schemas import TermDelta, TrendReport, WindowSpec

_SPEC = WindowSpec(
    period="week",
    current_start=date(2026, 5, 15),
    current_end=date(2026, 5, 22),
    previous_start=date(2026, 5, 8),
    previous_end=date(2026, 5, 15),
)


def _report(**kw) -> TrendReport:
    base = dict(
        window=_SPEC, rising=[], fading=[], new=[], dropped=[], top_current=[],
        total_current_items=0, total_previous_items=0,
    )
    base.update(kw)
    return TrendReport(**base)


def test_render_includes_period_and_dates():
    md = render_markdown(_report(total_current_items=5, total_previous_items=3))
    assert "week" in md
    assert "2026-05-15" in md
    assert "2026-05-22" in md


def test_render_lists_rising_terms():
    rising = [TermDelta(term="rag", current=8, previous=3, delta=5, importance=0.0)]
    md = render_markdown(_report(rising=rising))
    assert "rag" in md
    assert "5" in md  # delta


def test_render_empty_sections_marked():
    md = render_markdown(_report())
    assert "(없음)" in md
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/slices/trends/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.slices.trends.report`

- [ ] **Step 3: `src/newsletter/slices/trends/report.py` 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/slices/trends/test_report.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: ruff + 커밋**

Run: `uv run ruff check src/newsletter/slices/trends/report.py tests/slices/trends/test_report.py` → clean.

```bash
git add src/newsletter/slices/trends/report.py tests/slices/trends/test_report.py
git commit -m "feat(trends): markdown report rendering"
```

---

## Task 6: trends/cli.py + 루트 등록

**Files:**
- Create: `src/newsletter/slices/trends/cli.py`
- Modify: `src/newsletter/cli.py`
- Test: `tests/slices/trends/test_cli.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/slices/trends/test_cli.py`**

```python
"""trends CLI smoke tests."""

from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate
from newsletter.slices.trends.cli import app

runner = CliRunner()


def _seed_source(db_session) -> None:
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


def _seed(db_session, *, title: str, published_at: datetime) -> None:
    raw = RawItem(
        source_id="src",
        title=title,
        url=f"https://example.com/{title[:20]}-{published_at}",
        published_at=published_at,
        raw_summary=title,
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    proc = ProcessedItem(
        raw_item_id=raw.id,
        normalized_title=title,
        canonical_url=raw.url,
        content_track="expert_news",
        category="AI Model",
        relevance_score=0.9,
        importance_score=1.0,
        summary=title,
        keywords=None,
        duplicate_group_id=None,
    )
    db_session.add(proc)
    db_session.flush()


def test_trends_empty_window(db_session):
    result = runner.invoke(app, ["--period", "week", "--end", "2026-05-21"])
    assert result.exit_code == 0
    assert "no items in window" in result.output.lower()


def test_trends_reports_new_term(db_session):
    _seed_source(db_session)
    _seed(db_session, title="Sora video model launch", published_at=datetime(2026, 5, 18, 9, 0))
    db_session.commit()
    result = runner.invoke(
        app, ["--period", "week", "--end", "2026-05-21", "--min-count", "1"]
    )
    assert result.exit_code == 0, result.output
    assert "sora" in result.output.lower()


def test_trends_saves_to_file(tmp_path, db_session):
    _seed_source(db_session)
    _seed(db_session, title="Sora video model", published_at=datetime(2026, 5, 18, 9, 0))
    db_session.commit()
    out = tmp_path / "trends.md"
    result = runner.invoke(
        app,
        ["--period", "week", "--end", "2026-05-21", "--min-count", "1", "--save", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "트렌드 리포트" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/slices/trends/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.slices.trends.cli`

- [ ] **Step 3: `src/newsletter/slices/trends/cli.py` 구현**

```python
"""``newsletter trends`` — period-over-period title-keyword trend report.

Deterministic: counts distinct title terms across two equal-length windows
(current vs previous) and prints rising/fading/new/dropped terms. No LLM.
"""

from __future__ import annotations

from datetime import date as date_cls
from pathlib import Path

import typer

from newsletter.core.db import session_scope
from newsletter.slices.trends.report import render_markdown
from newsletter.slices.trends.service import analyze_trends

app = typer.Typer(
    name="trends",
    help="Period-over-period AI topic trend report from accumulated items.",
    invoke_without_command=True,
    no_args_is_help=False,
)


def _resolve_end(value: str | None) -> date_cls:
    if value is None or value == "today":
        return date_cls.today()
    return date_cls.fromisoformat(value)


@app.callback(invoke_without_command=True)
def cmd_trends(
    period: str = typer.Option("week", "--period", help="week or month."),
    end: str | None = typer.Option(
        None, "--end", help="End date YYYY-MM-DD or 'today' (default today)."
    ),
    top: int = typer.Option(15, "--top", help="Max terms per section."),
    min_count: int = typer.Option(
        2, "--min-count", help="Ignore terms below this article count."
    ),
    save: str | None = typer.Option(
        None, "--save", help="Write markdown to this path instead of stdout."
    ),
) -> None:
    """Print (or save) the period-over-period trend report."""
    if period not in ("week", "month"):
        typer.echo("period must be 'week' or 'month'", err=True)
        raise typer.Exit(code=1)
    with session_scope() as session:
        report = analyze_trends(
            session, period=period, end=_resolve_end(end), top_n=top, min_count=min_count
        )

    if report.total_current_items == 0 and report.total_previous_items == 0:
        typer.echo("(no items in window)")
        return

    markdown = render_markdown(report)
    if save:
        Path(save).write_text(markdown, encoding="utf-8")
        typer.echo(f"트렌드 리포트 저장: {save}")
    else:
        typer.echo(markdown)
```

- [ ] **Step 4: 루트 CLI 등록 — `src/newsletter/cli.py`**

import 영역(다른 슬라이스 cli import와 같은 곳, `# noqa: E402` 스타일)에 추가:
```python
from newsletter.slices.trends.cli import app as trends_app  # noqa: E402
```
`app.add_typer(stats_app, name="stats")` 다음 줄에 추가:
```python
app.add_typer(trends_app, name="trends")
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/slices/trends/test_cli.py -v`
Expected: PASS (3 passed)

Note: like the corpus CLI tests, `db_session` sets up the shared in-memory engine that `session_scope` reuses. If `test_trends_reports_new_term` shows nothing, confirm the seed committed and `--min-count 1` is passed (a single article needs min_count=1 to surface).

- [ ] **Step 6: ruff + 커밋**

Run: `uv run ruff check src/newsletter/slices/trends/cli.py src/newsletter/cli.py tests/slices/trends/test_cli.py` → clean (use `--fix` for import order if needed).

```bash
git add src/newsletter/slices/trends/cli.py src/newsletter/cli.py tests/slices/trends/test_cli.py
git commit -m "feat(trends): CLI (newsletter trends) + root registration"
```

---

## Task 7: 문서 (AGENTS.md) + 전체 검증

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: AGENTS.md 갱신**

`AGENTS.md` 를 먼저 읽어 형식을 파악한 뒤, 기존 슬라이스/명령 표기 형식 그대로 추가한다(새 형식 만들지 않음):
- 슬라이스 트리/목록에 `trends/` — 누적 ProcessedItem 제목 키워드의 주간/월간 변화 리포트.
- CLI 명령 목록(Run 섹션)에 `newsletter trends [--period week|month] [--end DATE] [--top N] [--min-count N] [--save PATH]`.

(설정 env var는 없음 — 추가하지 않는다.)

- [ ] **Step 2: 전체 테스트 + 린트**

Run: `uv run pytest`
Expected: 모두 통과 (직전 535 + 신규 약 21 = 약 556). 정확한 합계를 보고한다.

Run: `uv run ruff check src/newsletter/slices/trends src/newsletter/core/text.py src/newsletter/slices/corpus/chunking.py src/newsletter/cli.py`
Expected: clean. (전역 `ruff format` 은 돌리지 않는다 — 변경 파일만 `ruff check --fix`.)

- [ ] **Step 3: 커밋**

```bash
git add AGENTS.md
git commit -m "docs(trends): document trends slice + CLI in AGENTS.md"
```

---

## 검증 체크리스트 (전체 완료 후)

- [ ] `uv run pytest` 전부 통과.
- [ ] corpus 회귀 없음(`tests/slices/corpus/test_chunking.py` 통과 — extract_keywords 불변).
- [ ] `newsletter trends` 빈 윈도우 시 "(no items in window)" 안내.
- [ ] `newsletter trends --save PATH` 가 마크다운 파일 작성.
- [ ] 신규/수정 파일 `ruff check` 통과.
- [ ] 핸드오프 노트(`hitl/`) 갱신 — Phase 3 두 번째 항목 완료 기록.
```
