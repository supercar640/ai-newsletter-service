# Competitor Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `competitors` slice that detects operator-registered competitor mentions (name + aliases) in accumulated ProcessedItems and produces a standalone competitor-mention report (CLI + markdown).

**Architecture:** New `competitors` table (mirrors the `company_interests` registry pattern) plus a self-contained vertical slice `matching / repository / schemas / service / report / cli`. Detection is deterministic alias matching only — no LLM, no embeddings. The report is recomputed on demand over a single look-back window; nothing is persisted on ProcessedItem.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 ORM, Alembic, Pydantic v2, Typer, pytest. SQLite (in-memory for tests).

---

## Design Source

Full design: `docs/superpowers/specs/2026-05-21-competitor-monitoring-design.md`. Brainstorming is **already complete** — do not re-brainstorm. This plan operationalizes that design.

## File Structure

| Kind | Path | Responsibility |
|---|---|---|
| Create (model) | `src/newsletter/models/competitor.py` | `Competitor` ORM row (name, aliases_json, enabled, created_at) |
| Create (slice) | `src/newsletter/slices/competitors/__init__.py` | empty package marker |
| Create | `src/newsletter/slices/competitors/matching.py` | Pure: `CompetitorProfile`, `alias_matches`, `mentioned_competitor_ids` |
| Create | `src/newsletter/slices/competitors/schemas.py` | Pydantic CRUD schemas + report dataclasses |
| Create | `src/newsletter/slices/competitors/repository.py` | DB: registry CRUD + alias (de)serialization |
| Create | `src/newsletter/slices/competitors/service.py` | DB: window query → detect → `CompetitorReport` |
| Create | `src/newsletter/slices/competitors/report.py` | Pure: `CompetitorReport` → markdown |
| Create | `src/newsletter/slices/competitors/cli.py` | `newsletter competitors add/list/remove/enable/disable/report` |
| Modify | `src/newsletter/models/__init__.py` | register `Competitor` |
| Modify | `src/newsletter/cli.py` | mount `competitors` sub-app |
| Modify | `AGENTS.md` | document the new command + slice |
| Create (migration) | `migrations/versions/<rev>_add_competitors_table.py` | additive `competitors` table |
| Create (tests) | `tests/slices/competitors/{__init__,test_matching,test_repository,test_service,test_report,test_cli}.py` | per-module tests |

Each task is one slice file + its test, committed independently.

---

### Task 1: matching.py (pure, zero dependencies)

**Files:**
- Create: `src/newsletter/slices/competitors/__init__.py` (empty)
- Create: `src/newsletter/slices/competitors/matching.py`
- Create: `tests/slices/competitors/__init__.py` (empty)
- Test: `tests/slices/competitors/test_matching.py`

- [ ] **Step 1: Create the package markers**

Create `src/newsletter/slices/competitors/__init__.py` with a single docstring line:

```python
"""Competitor monitoring — deterministic alias-match mention report."""
```

Create `tests/slices/competitors/__init__.py` as an empty file (no content).

- [ ] **Step 2: Write the failing test**

Create `tests/slices/competitors/test_matching.py`:

```python
"""competitors.matching — pure alias matching."""

from __future__ import annotations

from newsletter.slices.competitors.matching import (
    CompetitorProfile,
    alias_matches,
    mentioned_competitor_ids,
)


def test_ascii_alias_matches_on_word_boundary():
    # "meta" must NOT match inside "metadata"
    assert alias_matches("openai released metadata tooling", "meta") is False
    assert alias_matches("meta launched llama 4", "meta") is True


def test_non_ascii_alias_matches_as_substring():
    # Korean particles attach with no boundary, so substring matching is required.
    assert alias_matches("네이버가 하이퍼클로바를 공개했다", "하이퍼클로바") is True
    assert alias_matches("카카오 소식", "하이퍼클로바") is False


def test_matching_is_case_insensitive_for_ascii():
    # text is pre-lowered by the caller; alias is stored lowered too.
    assert alias_matches("openai ships gpt-5", "openai") is True


def test_empty_alias_is_ignored():
    assert alias_matches("anything at all", "") is False


def test_mentioned_competitor_ids_returns_all_matches():
    competitors = [
        CompetitorProfile(id=1, name="OpenAI", aliases=("openai", "gpt")),
        CompetitorProfile(id=2, name="Google", aliases=("gemini", "deepmind")),
        CompetitorProfile(id=3, name="Anthropic", aliases=("claude",)),
    ]
    text = "openai and gemini both shipped models today"
    assert mentioned_competitor_ids(text, competitors) == {1, 2}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/slices/competitors/test_matching.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.competitors.matching'`

- [ ] **Step 4: Write minimal implementation**

Create `src/newsletter/slices/competitors/matching.py`:

```python
"""Pure alias matching for competitor detection (no IO).

ASCII aliases match on word boundaries so "meta" does not match
"metadata". Non-ASCII aliases (Korean, etc.) match as substrings because
Korean particles attach with no whitespace boundary, making ``\\b`` unusable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompetitorProfile:
    """An enabled competitor reduced to what matching needs.

    ``aliases`` are already lowercased by the caller.
    """

    id: int
    name: str
    aliases: tuple[str, ...]


def alias_matches(text_lower: str, alias_lower: str) -> bool:
    """True if ``alias_lower`` occurs in the already-lowercased ``text_lower``."""
    if not alias_lower:
        return False
    if alias_lower.isascii():
        return re.search(rf"\b{re.escape(alias_lower)}\b", text_lower) is not None
    return alias_lower in text_lower


def mentioned_competitor_ids(
    text_lower: str, competitors: list[CompetitorProfile]
) -> set[int]:
    """Ids of competitors with any alias present in the text."""
    return {
        c.id
        for c in competitors
        if any(alias_matches(text_lower, a) for a in c.aliases)
    }


__all__ = ["CompetitorProfile", "alias_matches", "mentioned_competitor_ids"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/slices/competitors/test_matching.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/competitors tests/slices/competitors
uv run ruff format src/newsletter/slices/competitors tests/slices/competitors
git add src/newsletter/slices/competitors tests/slices/competitors
git commit -m "feat(competitors): pure alias matching (matching.py)"
```

---

### Task 2: Competitor model + registration + migration

**Files:**
- Create: `src/newsletter/models/competitor.py`
- Modify: `src/newsletter/models/__init__.py`
- Create: `migrations/versions/<rev>_add_competitors_table.py` (autogenerated)
- Test: (covered indirectly; the autogenerate + upgrade is the verification)

- [ ] **Step 1: Write the model**

Create `src/newsletter/models/competitor.py`:

```python
"""Competitor — operator-registered companies/products to track in mentions.

Each row is one competitor. ``aliases_json`` holds the product/brand names
that the mention report matches against the title + summary of accumulated
ProcessedItems. Detection is deterministic alias matching — no embedding.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from newsletter.core.db import Base


class Competitor(Base):
    """One competitor the operator wants to track across collected items."""

    __tablename__ = "competitors"
    __table_args__ = (UniqueConstraint("name", name="uq_competitors_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"Competitor(id={self.id}, name={self.name!r}, enabled={self.enabled})"
```

- [ ] **Step 2: Register the model**

Edit `src/newsletter/models/__init__.py`. Add the import (alphabetical, after `company_interest`):

```python
from newsletter.models.company_interest import CompanyInterest
from newsletter.models.competitor import Competitor
from newsletter.models.context_chunk import ContextChunk
```

And add `"Competitor",` to `__all__` (after `"CompanyInterest",`):

```python
__all__ = [
    "CompanyInterest",
    "Competitor",
    "ContextChunk",
    "Department",
    "DepartmentTip",
    "NewsletterIssue",
    "ProcessedItem",
    "RawItem",
    "RunLog",
    "Source",
]
```

- [ ] **Step 3: Autogenerate the migration**

Run: `uv run alembic revision --autogenerate -m "add competitors table"`
Expected: a new file `migrations/versions/<rev>_add_competitors_table.py` whose `down_revision` is `'ddc1e6feada8'` (the current head) and whose `upgrade()` calls `op.create_table('competitors', ...)`.

- [ ] **Step 4: Inspect the generated migration**

Open the new file. Confirm `upgrade()` creates `competitors` with columns `id, name, aliases_json, enabled, created_at`, a `PrimaryKeyConstraint('id')`, and `UniqueConstraint('name', name='uq_competitors_name')`; confirm `downgrade()` calls `op.drop_table('competitors')`. Remove any unrelated incidental ops (there should be none — the change is purely additive). If `created_at` server_default is rendered, leave it as autogenerated.

- [ ] **Step 5: Apply and round-trip the migration**

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: all three succeed with no errors; `alembic heads` now shows the new revision.

- [ ] **Step 6: Commit**

```bash
git add src/newsletter/models/competitor.py src/newsletter/models/__init__.py migrations/versions
git commit -m "feat(competitors): Competitor model + migration"
```

---

### Task 3: schemas.py + repository.py

**Files:**
- Create: `src/newsletter/slices/competitors/schemas.py`
- Create: `src/newsletter/slices/competitors/repository.py`
- Test: `tests/slices/competitors/test_repository.py`

- [ ] **Step 1: Write schemas.py**

Create `src/newsletter/slices/competitors/schemas.py`:

```python
"""Schemas for the competitor registry and the mention report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class CompetitorCreate(BaseModel):
    """Input for registering a new competitor."""

    name: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list)
    enabled: bool = True


class CompetitorUpdate(BaseModel):
    """Partial update — every field optional."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    aliases: list[str] | None = None
    enabled: bool | None = None


class CompetitorRead(BaseModel):
    """Output shape exposed to callers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    aliases: list[str]
    enabled: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Headline:
    """One mentioning article."""

    title: str
    url: str
    importance: float


@dataclass(frozen=True, slots=True)
class CompetitorMentions:
    """Per-competitor rollup in a report."""

    name: str
    count: int
    headlines: list[Headline]  # importance desc, truncated to top_k


@dataclass(frozen=True, slots=True)
class CompetitorReport:
    """Result of analyzing one look-back window."""

    since: date
    until: date  # exclusive upper bound
    total_items: int  # items scanned in window
    competitors: list[CompetitorMentions]  # count desc, then name asc
```

- [ ] **Step 2: Write the failing repository test**

Create `tests/slices/competitors/test_repository.py`:

```python
"""competitors.repository — registry CRUD + alias (de)serialization."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from newsletter.slices.competitors import repository
from newsletter.slices.competitors.schemas import CompetitorCreate, CompetitorUpdate


def test_add_and_load_aliases(db_session: Session):
    row = repository.add(
        db_session,
        CompetitorCreate(name="OpenAI", aliases=["OpenAI", " GPT ", ""]),
    )
    db_session.commit()
    assert row.id is not None
    # blanks stripped, empties dropped
    assert repository.load_aliases(row) == ["OpenAI", "GPT"]


def test_add_duplicate_name_raises(db_session: Session):
    repository.add(db_session, CompetitorCreate(name="OpenAI"))
    db_session.commit()
    with pytest.raises(repository.CompetitorAlreadyExistsError):
        repository.add(db_session, CompetitorCreate(name="OpenAI"))


def test_list_only_enabled_filters(db_session: Session):
    repository.add(db_session, CompetitorCreate(name="OpenAI", enabled=True))
    repository.add(db_session, CompetitorCreate(name="Cohere", enabled=False))
    db_session.commit()
    all_rows = repository.list_competitors(db_session)
    enabled = repository.list_competitors(db_session, only_enabled=True)
    assert len(all_rows) == 2
    assert [r.name for r in enabled] == ["OpenAI"]


def test_update_replaces_aliases(db_session: Session):
    row = repository.add(db_session, CompetitorCreate(name="Google", aliases=["bard"]))
    db_session.commit()
    repository.update(db_session, row.id, CompetitorUpdate(aliases=["gemini", "deepmind"]))
    db_session.commit()
    db_session.expire_all()
    assert repository.load_aliases(repository.get(db_session, row.id)) == [
        "gemini",
        "deepmind",
    ]


def test_disable_and_remove(db_session: Session):
    row = repository.add(db_session, CompetitorCreate(name="Meta"))
    db_session.commit()
    repository.disable(db_session, row.id)
    db_session.commit()
    db_session.expire_all()
    assert repository.get(db_session, row.id).enabled is False
    repository.remove(db_session, row.id)
    db_session.commit()
    assert repository.get(db_session, row.id) is None


def test_load_aliases_tolerates_malformed_json(db_session: Session):
    row = repository.add(db_session, CompetitorCreate(name="X"))
    row.aliases_json = "{not json"
    db_session.flush()
    assert repository.load_aliases(row) == []


def test_get_or_raise_missing(db_session: Session):
    with pytest.raises(repository.CompetitorNotFoundError):
        repository.get_or_raise(db_session, 999)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/slices/competitors/test_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.competitors.repository'`

- [ ] **Step 4: Write repository.py**

Create `src/newsletter/slices/competitors/repository.py`:

```python
"""Data access for Competitor rows.

Aliases are stored as JSON text on the row; the repository handles the
(de)serialization so the rest of the slice deals with plain ``list[str]``.
Mirrors the interests-registry pattern.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from newsletter.models.competitor import Competitor
from newsletter.slices.competitors.schemas import CompetitorCreate, CompetitorUpdate


class CompetitorAlreadyExistsError(Exception):
    """Raised when ``add`` is called with an already-used name."""


class CompetitorNotFoundError(Exception):
    """Raised when an operation references a missing competitor id."""


def list_competitors(session: Session, *, only_enabled: bool = False) -> list[Competitor]:
    stmt = select(Competitor).order_by(Competitor.id)
    if only_enabled:
        stmt = stmt.where(Competitor.enabled.is_(True))
    return list(session.scalars(stmt).all())


def get(session: Session, competitor_id: int) -> Competitor | None:
    return session.get(Competitor, competitor_id)


def get_or_raise(session: Session, competitor_id: int) -> Competitor:
    row = get(session, competitor_id)
    if row is None:
        raise CompetitorNotFoundError(competitor_id)
    return row


def add(session: Session, payload: CompetitorCreate) -> Competitor:
    row = Competitor(
        name=payload.name,
        aliases_json=_dump_aliases(payload.aliases),
        enabled=payload.enabled,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise CompetitorAlreadyExistsError(payload.name) from exc
    return row


def update(session: Session, competitor_id: int, payload: CompetitorUpdate) -> Competitor:
    row = get_or_raise(session, competitor_id)
    changes = payload.model_dump(exclude_unset=True)
    if "aliases" in changes and changes["aliases"] is not None:
        row.aliases_json = _dump_aliases(changes["aliases"])
        del changes["aliases"]
    for key, value in changes.items():
        setattr(row, key, value)
    session.flush()
    return row


def disable(session: Session, competitor_id: int) -> Competitor:
    row = get_or_raise(session, competitor_id)
    row.enabled = False
    session.flush()
    return row


def remove(session: Session, competitor_id: int) -> None:
    row = get_or_raise(session, competitor_id)
    session.delete(row)
    session.flush()


def load_aliases(row: Competitor) -> list[str]:
    """Parse the JSON aliases column. Tolerant of malformed payloads."""
    try:
        parsed = json.loads(row.aliases_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(a) for a in parsed if a]


def _dump_aliases(aliases: Sequence[str]) -> str:
    cleaned = [a.strip() for a in aliases if a and a.strip()]
    return json.dumps(cleaned, ensure_ascii=False)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/slices/competitors/test_repository.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/competitors tests/slices/competitors
uv run ruff format src/newsletter/slices/competitors tests/slices/competitors
git add src/newsletter/slices/competitors tests/slices/competitors
git commit -m "feat(competitors): schemas + registry repository"
```

---

### Task 4: service.py (window query → detect → CompetitorReport)

**Files:**
- Create: `src/newsletter/slices/competitors/service.py`
- Test: `tests/slices/competitors/test_service.py`

- [ ] **Step 1: Write the failing service test**

Create `tests/slices/competitors/test_service.py`:

```python
"""competitors.service — window query + alias detection."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.competitors import repository
from newsletter.slices.competitors.schemas import CompetitorCreate
from newsletter.slices.competitors.service import analyze_competitors
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

_UNTIL = date(2026, 5, 22)  # exclusive upper bound used in tests


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
    importance: float,
    published_at: datetime | None,
    created_at: datetime | None = None,
) -> None:
    raw = RawItem(
        source_id="src",
        title=title,
        url=f"https://example.com/{title[:24]}-{published_at}-{created_at}",
        published_at=published_at,
        raw_summary=summary,
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
        importance_score=importance,
        summary=summary,
        keywords=None,
        duplicate_group_id=None,
        **kwargs,
    )
    db_session.add(proc)
    db_session.flush()


def test_counts_and_window_filtering(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai", "gpt"]))
    # in window
    _seed_item(
        db_session,
        title="OpenAI ships GPT-5",
        summary="big day",
        importance=2.0,
        published_at=datetime(2026, 5, 20, 9, 0),
    )
    # outside window (too old)
    _seed_item(
        db_session,
        title="OpenAI old news",
        summary="last month",
        importance=1.0,
        published_at=datetime(2026, 4, 1, 9, 0),
    )
    db_session.commit()

    report = analyze_competitors(db_session, days=7, until=_UNTIL)
    assert report.total_items == 1  # only the in-window item scanned
    assert len(report.competitors) == 1
    mentions = report.competitors[0]
    assert mentions.name == "OpenAI"
    assert mentions.count == 1
    assert mentions.headlines[0].title == "OpenAI ships GPT-5"


def test_multiple_competitors_attributed(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    repository.add(db_session, CompetitorCreate(name="Google", aliases=["gemini"]))
    _seed_item(
        db_session,
        title="OpenAI and Gemini both ship",
        summary="rivalry",
        importance=3.0,
        published_at=datetime(2026, 5, 20, 9, 0),
    )
    db_session.commit()

    report = analyze_competitors(db_session, days=7, until=_UNTIL)
    by_name = {m.name: m for m in report.competitors}
    assert by_name["OpenAI"].count == 1
    assert by_name["Google"].count == 1
    # ordering: count desc then name asc -> tie broken by name
    assert [m.name for m in report.competitors] == ["Google", "OpenAI"]


def test_disabled_competitor_excluded(db_session: Session):
    _seed_source(db_session)
    repository.add(
        db_session, CompetitorCreate(name="OpenAI", aliases=["openai"], enabled=False)
    )
    _seed_item(
        db_session,
        title="OpenAI ships",
        summary="x",
        importance=1.0,
        published_at=datetime(2026, 5, 20, 9, 0),
    )
    db_session.commit()
    report = analyze_competitors(db_session, days=7, until=_UNTIL)
    assert report.competitors == []


def test_published_at_null_falls_back_to_created_at(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    _seed_item(
        db_session,
        title="OpenAI fallback",
        summary="x",
        importance=1.0,
        published_at=None,
        created_at=datetime(2026, 5, 20, 9, 0),
    )
    db_session.commit()
    report = analyze_competitors(db_session, days=7, until=_UNTIL)
    assert report.total_items == 1
    assert report.competitors[0].count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/slices/competitors/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.competitors.service'`

- [ ] **Step 3: Write service.py**

Create `src/newsletter/slices/competitors/service.py`:

```python
"""Competitor mention analysis over accumulated ProcessedItem rows.

The service is the only place that touches the DB. It resolves a single
look-back window, anchors each item by published_at (falling back to
created_at), runs deterministic alias matching, and rolls the matches up
into a CompetitorReport. No LLM, no embeddings.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.competitors import repository
from newsletter.slices.competitors.matching import (
    CompetitorProfile,
    mentioned_competitor_ids,
)
from newsletter.slices.competitors.schemas import (
    CompetitorMentions,
    CompetitorReport,
    Headline,
)


def analyze_competitors(
    session: Session,
    *,
    days: int = 7,
    until: date | None = None,
    since: date | None = None,
    top_k: int = 5,
) -> CompetitorReport:
    """Build a CompetitorReport over a single look-back window.

    Window is half-open ``[since, until)``. ``until`` defaults to tomorrow
    (so today is included); ``since`` defaults to ``until - days`` but an
    explicit ``since`` wins. Each enabled competitor is included even with a
    zero count (watch-list semantics).
    """
    until_date = until or (date.today() + timedelta(days=1))
    since_date = since or (until_date - timedelta(days=days))
    lo = datetime.combine(since_date, time.min)
    hi = datetime.combine(until_date, time.min)

    profiles = _load_profiles(session)
    # name + zero-count seed for every enabled competitor (watch-list)
    counts: dict[int, int] = {p.id: 0 for p in profiles}
    headlines: dict[int, list[Headline]] = {p.id: [] for p in profiles}
    names: dict[int, str] = {p.id: p.name for p in profiles}

    total_items = 0
    for title, summary, url, importance, published_at, created_at in _fetch(session, lo, hi):
        anchor = _anchor(published_at, created_at)
        if anchor is None or not (lo <= anchor < hi):
            continue
        total_items += 1
        text_lower = f"{title or ''} {summary or ''}".lower()
        for cid in mentioned_competitor_ids(text_lower, profiles):
            counts[cid] += 1
            headlines[cid].append(
                Headline(title=title, url=url, importance=importance or 0.0)
            )

    mentions = [
        CompetitorMentions(
            name=names[cid],
            count=counts[cid],
            headlines=sorted(headlines[cid], key=lambda h: h.importance, reverse=True)[
                :top_k
            ],
        )
        for cid in counts
    ]
    mentions.sort(key=lambda m: (-m.count, m.name))

    return CompetitorReport(
        since=since_date,
        until=until_date,
        total_items=total_items,
        competitors=mentions,
    )


def _load_profiles(session: Session) -> list[CompetitorProfile]:
    rows = repository.list_competitors(session, only_enabled=True)
    return [
        CompetitorProfile(
            id=row.id,
            name=row.name,
            aliases=tuple(a.lower() for a in repository.load_aliases(row)),
        )
        for row in rows
    ]


def _fetch(session: Session, lo: datetime, hi: datetime):
    """Rows whose anchor (published_at, else created_at) falls in [lo, hi)."""
    stmt = (
        select(
            ProcessedItem.normalized_title,
            ProcessedItem.summary,
            ProcessedItem.canonical_url,
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


__all__ = ["analyze_competitors"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/slices/competitors/test_service.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/competitors tests/slices/competitors
uv run ruff format src/newsletter/slices/competitors tests/slices/competitors
git add src/newsletter/slices/competitors tests/slices/competitors
git commit -m "feat(competitors): window query + alias detection service"
```

---

### Task 5: report.py (CompetitorReport → markdown)

**Files:**
- Create: `src/newsletter/slices/competitors/report.py`
- Test: `tests/slices/competitors/test_report.py`

- [ ] **Step 1: Write the failing report test**

Create `tests/slices/competitors/test_report.py`:

```python
"""competitors.report — deterministic markdown rendering."""

from __future__ import annotations

from datetime import date

from newsletter.slices.competitors.report import render_markdown
from newsletter.slices.competitors.schemas import (
    CompetitorMentions,
    CompetitorReport,
    Headline,
)


def _report(competitors):
    return CompetitorReport(
        since=date(2026, 5, 15),
        until=date(2026, 5, 22),
        total_items=42,
        competitors=competitors,
    )


def test_header_includes_window_and_scan_count():
    md = render_markdown(_report([]))
    assert "2026-05-15" in md
    assert "2026-05-22" in md
    assert "42" in md


def test_competitor_counts_and_headlines_in_importance_order():
    mentions = CompetitorMentions(
        name="OpenAI",
        count=2,
        headlines=[
            Headline(title="Top story", url="https://e.com/a", importance=3.0),
            Headline(title="Lesser story", url="https://e.com/b", importance=1.0),
        ],
    )
    md = render_markdown(_report([mentions]))
    assert "## OpenAI — 2건" in md
    assert "[Top story](https://e.com/a)" in md
    # importance order: top story precedes lesser story in the text
    assert md.index("Top story") < md.index("Lesser story")


def test_zero_count_competitor_shows_no_mention_marker():
    mentions = CompetitorMentions(name="Cohere", count=0, headlines=[])
    md = render_markdown(_report([mentions]))
    assert "## Cohere — 0건" in md
    assert "(언급 없음)" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/slices/competitors/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.competitors.report'`

- [ ] **Step 3: Write report.py**

Create `src/newsletter/slices/competitors/report.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/slices/competitors/test_report.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/competitors tests/slices/competitors
uv run ruff format src/newsletter/slices/competitors tests/slices/competitors
git add src/newsletter/slices/competitors tests/slices/competitors
git commit -m "feat(competitors): markdown report rendering"
```

---

### Task 6: cli.py + root registration

**Files:**
- Create: `src/newsletter/slices/competitors/cli.py`
- Modify: `src/newsletter/cli.py`
- Test: `tests/slices/competitors/test_cli.py`

- [ ] **Step 1: Write the failing CLI test**

Create `tests/slices/competitors/test_cli.py`:

```python
"""competitors CLI smoke tests."""

from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.competitors import repository
from newsletter.slices.competitors.cli import app
from newsletter.slices.competitors.schemas import CompetitorCreate
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

runner = CliRunner()


def test_add_then_list(db_session):
    result = runner.invoke(
        app, ["add", "--name", "OpenAI", "--aliases", "openai,gpt"]
    )
    assert result.exit_code == 0, result.output
    assert "competitor 추가 완료" in result.output

    db_session.expire_all()
    rows = repository.list_competitors(db_session)
    assert len(rows) == 1
    assert rows[0].name == "OpenAI"

    listed = runner.invoke(app, ["list"])
    assert listed.exit_code == 0
    assert "OpenAI" in listed.output


def test_report_without_competitors_is_graceful(db_session):
    result = runner.invoke(app, ["report"])
    assert result.exit_code == 0
    assert "no competitors registered" in result.output


def test_report_smoke(db_session):
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
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    raw = RawItem(
        source_id="src",
        title="OpenAI ships",
        url="https://example.com/x",
        published_at=datetime(2026, 5, 20, 9, 0),
        raw_summary="news",
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title="OpenAI ships",
            canonical_url="https://example.com/x",
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=1.0,
            summary="news",
        )
    )
    db_session.commit()

    result = runner.invoke(app, ["report", "--since", "2026-05-15", "--until", "2026-05-22"])
    assert result.exit_code == 0, result.output
    assert "OpenAI" in result.output


def test_report_save_writes_file(db_session, tmp_path):
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    db_session.commit()
    out = tmp_path / "report.md"
    result = runner.invoke(
        app,
        ["report", "--since", "2026-05-15", "--until", "2026-05-22", "--save", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "경쟁사 멘션 리포트" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/slices/competitors/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.slices.competitors.cli'`

- [ ] **Step 3: Write cli.py**

Create `src/newsletter/slices/competitors/cli.py`:

```python
"""``newsletter competitors`` — registry CRUD + mention report.

Deterministic alias matching over accumulated items. No LLM, no embeddings.
"""

from __future__ import annotations

from datetime import date as date_cls
from pathlib import Path

import typer

from newsletter.core.db import session_scope
from newsletter.slices.competitors import repository
from newsletter.slices.competitors.report import render_markdown
from newsletter.slices.competitors.schemas import CompetitorCreate, CompetitorUpdate
from newsletter.slices.competitors.service import analyze_competitors

app = typer.Typer(
    help="Track competitor mentions across collected items.",
    no_args_is_help=True,
    add_completion=False,
)


def _split_aliases(value: str | None) -> list[str]:
    if not value:
        return []
    return [a.strip() for a in value.split(",") if a.strip()]


@app.command("list")
def cmd_list() -> None:
    """List registered competitors."""
    with session_scope() as session:
        rows = repository.list_competitors(session)
        if not rows:
            typer.echo("(no competitors registered)")
            return
        header = f"{'id':>4} {'enabled':>8}  name / aliases"
        typer.echo(header)
        typer.echo("-" * len(header))
        for r in rows:
            aliases = ", ".join(repository.load_aliases(r))
            typer.echo(
                f"{r.id:>4} {('on' if r.enabled else 'off'):>8}  {r.name}  [{aliases}]"
            )


@app.command("add")
def cmd_add(
    name: str = typer.Option(..., "--name", help="Display name (unique)."),
    aliases: str = typer.Option(
        "", "--aliases", help="Comma-separated aliases / product names to match."
    ),
) -> None:
    """Register a competitor."""
    payload = CompetitorCreate(name=name, aliases=_split_aliases(aliases))
    with session_scope() as session:
        try:
            row = repository.add(session, payload)
        except repository.CompetitorAlreadyExistsError:
            typer.echo(f"이미 존재하는 이름입니다: {name}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"competitor 추가 완료: id={row.id} name={row.name}")


@app.command("disable")
def cmd_disable(
    competitor_id: int = typer.Argument(..., help="Competitor id to disable."),
) -> None:
    """Disable a competitor (excluded from detection)."""
    with session_scope() as session:
        try:
            row = repository.disable(session, competitor_id)
        except repository.CompetitorNotFoundError:
            typer.echo(f"존재하지 않는 id: {competitor_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"competitor 비활성화: id={row.id} name={row.name}")


@app.command("enable")
def cmd_enable(
    competitor_id: int = typer.Argument(..., help="Competitor id."),
) -> None:
    """Re-enable a previously disabled competitor."""
    with session_scope() as session:
        try:
            row = repository.update(
                session, competitor_id, CompetitorUpdate(enabled=True)
            )
        except repository.CompetitorNotFoundError:
            typer.echo(f"존재하지 않는 id: {competitor_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"competitor 활성화: id={row.id} name={row.name}")


@app.command("remove")
def cmd_remove(
    competitor_id: int = typer.Argument(..., help="Competitor id to remove."),
) -> None:
    """Delete a competitor. Irreversible."""
    with session_scope() as session:
        try:
            repository.remove(session, competitor_id)
        except repository.CompetitorNotFoundError:
            typer.echo(f"존재하지 않는 id: {competitor_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"competitor 삭제 완료: id={competitor_id}")


@app.command("report")
def cmd_report(
    days: int = typer.Option(7, "--days", help="Look-back window length in days."),
    since: str | None = typer.Option(
        None, "--since", help="Window start YYYY-MM-DD (wins over --days)."
    ),
    until: str | None = typer.Option(
        None, "--until", help="Exclusive window end YYYY-MM-DD (default tomorrow)."
    ),
    top: int = typer.Option(5, "--top", help="Max headlines per competitor."),
    save: str | None = typer.Option(
        None, "--save", help="Write markdown to this path instead of stdout."
    ),
) -> None:
    """Print (or save) the competitor mention report."""
    since_date = date_cls.fromisoformat(since) if since else None
    until_date = date_cls.fromisoformat(until) if until else None
    with session_scope() as session:
        if not repository.list_competitors(session, only_enabled=True):
            typer.echo("(no competitors registered)")
            return
        report = analyze_competitors(
            session, days=days, until=until_date, since=since_date, top_k=top
        )

    markdown = render_markdown(report)
    if save:
        Path(save).write_text(markdown, encoding="utf-8")
        typer.echo(f"경쟁사 리포트 저장: {save}")
    else:
        typer.echo(markdown)
```

- [ ] **Step 4: Register the sub-app in the root CLI**

Edit `src/newsletter/cli.py`. Add the import (with the other slice imports, after the corpus import):

```python
from newsletter.slices.competitors.cli import app as competitors_app  # noqa: E402
```

Add the mount (after the `corpus` mount):

```python
app.add_typer(competitors_app, name="competitors")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/slices/competitors/test_cli.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Verify the root CLI wiring**

Run: `uv run newsletter competitors --help`
Expected: help text listing `add`, `list`, `remove`, `enable`, `disable`, `report` sub-commands.

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check --fix src/newsletter tests/slices/competitors
uv run ruff format src/newsletter tests/slices/competitors
git add src/newsletter/slices/competitors src/newsletter/cli.py tests/slices/competitors
git commit -m "feat(competitors): CLI commands + root registration"
```

---

### Task 7: AGENTS.md docs + full verification

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Add the command row**

Edit `AGENTS.md`. After the `trends` command row (currently line ~82), add:

```markdown
| `uv run newsletter competitors add \| list \| remove \| enable \| disable \| report [--days N \| --since DATE] [--until DATE] [--top K] [--save PATH]` | Register competitors and report their mentions across collected items |
```

- [ ] **Step 2: Add the slice tree entry**

Edit `AGENTS.md`. After the `trends/` slice-tree line (currently line ~131), add a sibling line matching the surrounding indentation:

```markdown
│   └── competitors/     운영자가 등록한 경쟁사(이름+별칭)를 누적 ProcessedItem에서 탐지해 멘션 수·대표 헤드라인을 보여주는 독립 리포트 슬라이스
```

(Adjust the `├──`/`└──` box-drawing characters so the previous entry and this one stay consistent with the existing tree — the last child uses `└──`.)

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -q`
Expected: all tests pass — the prior baseline was 560 passing; this slice adds ~23 (5 matching + 7 repository + 4 service + 3 report + 4 cli), so expect ~583 passing, 0 failed.

- [ ] **Step 4: Full lint + format check**

Run: `uv run ruff check && uv run ruff format --check`
Expected: no errors, no files would be reformatted.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md
git commit -m "docs(competitors): document command + slice in AGENTS.md"
```

---

## Self-Review Notes

- **Spec coverage:** registry CRUD (Tasks 3, 6), alias detection (Tasks 1, 4), per-competitor count + headlines report (Tasks 4, 5), graceful empty handling (Task 6 `report` guard + Task 5 `(언급 없음)`), additive migration (Task 2), single look-back window with `published_at→created_at` anchor (Task 4), ASCII word-boundary vs non-ASCII substring matching (Task 1). All design sections map to a task.
- **Type consistency:** `CompetitorProfile` defined in `matching.py` and consumed in `service.py`; `CompetitorCreate/Update/Read`, `Headline`, `CompetitorMentions`, `CompetitorReport` defined in `schemas.py` and consumed by repository/service/report/cli. `analyze_competitors` signature is identical across service (def) and cli (call). Repository method names (`add/list_competitors/get/get_or_raise/update/disable/remove/load_aliases`) are used consistently in service and cli.
- **No placeholders:** every code step shows complete code; every run step shows the exact command and expected outcome.
</content>
</invoke>
