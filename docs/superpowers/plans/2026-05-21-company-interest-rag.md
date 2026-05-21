# 회사 관심사 RAG (corpus 슬라이스) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사내 문서 디렉터리를 청크 단위로 인덱싱해 뉴스 아이템과의 의미적 관련도를 계산하고, 중요도 스코어에 추가 배수로 반영한다.

**Architecture:** 새 독립 버티컬 슬라이스 `corpus`(chunking·repository·indexer·cli)를 만든다. 스코어링은 기존 `integration/scoring.py`에 `corpus_relevance_factor`를 추가해 `base × interest_match × corpus_relevance`로 합성한다. 임베딩 키가 없으면 키워드 겹침으로 폴백하고, 청크가 없으면 배수 1.0(회귀 0)이다.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Alembic, Typer, pytest, Voyage 임베딩(`core/embeddings.py`).

**설계 문서:** `docs/superpowers/specs/2026-05-21-company-interest-rag-design.md`

---

## File Structure

| 파일 | 책임 |
|---|---|
| `src/newsletter/slices/corpus/chunking.py` (생성) | 순수: 텍스트 → 청크 + 키워드 추출 |
| `src/newsletter/models/context_chunk.py` (생성) | `context_chunks` ORM 모델 |
| `src/newsletter/models/__init__.py` (수정) | 새 모델 등록 |
| `src/newsletter/slices/corpus/repository.py` (생성) | 청크 DB 함수 |
| `src/newsletter/slices/corpus/indexer.py` (생성) | 디렉터리 스캔 → 임베딩 → 영속화 |
| `src/newsletter/slices/corpus/schemas.py` (생성) | `IndexReport` dataclass |
| `src/newsletter/slices/corpus/cli.py` (생성) | `corpus index/list/clear/status` |
| `src/newsletter/slices/corpus/__init__.py` (생성) | 빈 패키지 마커 |
| `src/newsletter/slices/integration/scoring.py` (수정) | `CorpusChunk` + `corpus_relevance_factor` + `score_items` 인자 |
| `src/newsletter/slices/integration/service.py` (수정) | `_load_corpus_chunks` + 전달 |
| `src/newsletter/core/config.py` (수정) | `company_context_dir` 설정 |
| `src/newsletter/cli.py` (수정) | `corpus_app` 루트 등록 |
| `.env.example`, `AGENTS.md` (수정) | 문서 |
| `migrations/versions/<rev>_*.py` (생성) | Alembic |

테스트는 `tests/slices/corpus/`(신규)와 `tests/slices/integration/`(기존)에 둔다.

---

## Task 1: chunking.py (순수 청크 분할 + 키워드 추출)

**Files:**
- Create: `src/newsletter/slices/corpus/__init__.py`
- Create: `src/newsletter/slices/corpus/chunking.py`
- Test: `tests/slices/corpus/__init__.py`, `tests/slices/corpus/test_chunking.py`

- [ ] **Step 1: 빈 패키지 마커 생성**

`src/newsletter/slices/corpus/__init__.py` 와 `tests/slices/corpus/__init__.py` 를 빈 파일로 생성한다.

```python
```

(두 파일 모두 내용 없음.)

- [ ] **Step 2: 실패 테스트 작성**

`tests/slices/corpus/test_chunking.py`:

```python
"""corpus.chunking — pure text splitting + keyword extraction."""

from __future__ import annotations

from newsletter.slices.corpus.chunking import chunk_text, extract_keywords


def test_chunk_splits_on_headings():
    text = "# 제목\n첫 문단입니다.\n\n## 둘째\n둘째 문단."
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert chunks[0].startswith("# 제목")
    assert chunks[1].startswith("## 둘째")


def test_chunk_packs_paragraphs_under_max():
    text = "문단 하나.\n\n문단 둘.\n\n문단 셋."
    chunks = chunk_text(text, max_chars=1000)
    assert chunks == ["문단 하나.\n\n문단 둘.\n\n문단 셋."]


def test_chunk_hard_splits_oversize_block():
    block = " ".join(["word"] * 500)  # > max_chars
    chunks = chunk_text(block, max_chars=100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)


def test_chunk_drops_empty_and_whitespace():
    assert chunk_text("\n\n   \n\n") == []


def test_extract_keywords_orders_by_frequency_then_alpha():
    text = "rag rag rag agent agent vector"
    kws = extract_keywords(text, max_keywords=3)
    assert kws == ["rag", "agent", "vector"]


def test_extract_keywords_drops_short_tokens_and_stopwords():
    text = "the a AI 및 모델 모델"
    kws = extract_keywords(text)
    assert "the" not in kws
    assert "및" not in kws
    assert "모델" in kws
    assert "ai" in kws
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `uv run pytest tests/slices/corpus/test_chunking.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.slices.corpus.chunking`

- [ ] **Step 4: chunking.py 구현**

`src/newsletter/slices/corpus/chunking.py`:

```python
"""Pure text chunking + keyword extraction for the company-context corpus.

No IO, no DB. The indexer wires these helpers to the filesystem and the
embedding client. Splitting is deterministic so re-indexing an unchanged
file yields identical chunks.
"""

from __future__ import annotations

import re
from collections import Counter

_HEADING_LINE_RE = re.compile(r"^#{1,6}\s")
_TOKEN_RE = re.compile(r"[0-9a-z가-힣]+")

# Light stopword set — common English glue words + Korean particles/fillers.
# Single-character tokens are dropped separately, so only len>1 entries matter.
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "but", "not", "you", "with", "this",
        "that", "from", "have", "was", "were", "한다", "합니다", "있다",
        "있습니다", "그리고", "그러나", "또는", "등의", "대한", "위한",
    }
)


def chunk_text(text: str, *, max_chars: int = 1200) -> list[str]:
    """Split a document into chunks at headings/paragraphs, capped at max_chars."""
    blocks: list[str] = []
    for block in _split_blocks(text):
        blocks.extend(_hard_split(block, max_chars))

    chunks: list[str] = []
    current = ""
    for block in blocks:
        if not current:
            current = block
        elif len(current) + 2 + len(block) <= max_chars:
            current = f"{current}\n\n{block}"
        else:
            chunks.append(current)
            current = block
    if current.strip():
        chunks.append(current)
    return [c.strip() for c in chunks if c.strip()]


def extract_keywords(text: str, *, max_keywords: int = 20) -> list[str]:
    """Frequency-ranked lowercased tokens. Deterministic (alpha tie-break)."""
    tokens = _TOKEN_RE.findall(text.lower())
    counts = Counter(t for t in tokens if len(t) > 1 and t not in _STOPWORDS)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [token for token, _ in ranked[:max_keywords]]


def _split_blocks(text: str) -> list[str]:
    """Break text on heading lines and blank-line paragraph boundaries."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            joined = "\n".join(buffer).strip()
            if joined:
                blocks.append(joined)
            buffer.clear()

    for line in normalized.split("\n"):
        if _HEADING_LINE_RE.match(line):
            flush()
            buffer.append(line)
        elif line.strip() == "":
            flush()
        else:
            buffer.append(line)
    flush()
    return blocks


def _hard_split(block: str, max_chars: int) -> list[str]:
    """Split an oversize block on whitespace; chop any single oversize word."""
    if len(block) <= max_chars:
        return [block]
    pieces: list[str] = []
    current = ""
    for word in block.split(" "):
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current = f"{current} {word}"
        else:
            pieces.append(current)
            current = word
    if current:
        pieces.append(current)

    result: list[str] = []
    for piece in pieces:
        while len(piece) > max_chars:
            result.append(piece[:max_chars])
            piece = piece[max_chars:]
        if piece:
            result.append(piece)
    return result


__all__ = ["chunk_text", "extract_keywords"]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/slices/corpus/test_chunking.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: 커밋**

```bash
git add src/newsletter/slices/corpus/__init__.py src/newsletter/slices/corpus/chunking.py tests/slices/corpus/
git commit -m "feat(corpus): pure text chunking + keyword extraction"
```

---

## Task 2: ContextChunk 모델 + 마이그레이션

**Files:**
- Create: `src/newsletter/models/context_chunk.py`
- Modify: `src/newsletter/models/__init__.py`
- Create: `migrations/versions/<rev>_add_context_chunks_table.py` (autogenerate)

- [ ] **Step 1: 모델 작성**

`src/newsletter/models/context_chunk.py`:

```python
"""ContextChunk — one chunk of an internal company document.

The corpus indexer splits files under ``COMPANY_CONTEXT_DIR`` into chunks,
embeds each, and stores them here. The importance scorer matches news items
against these chunks (embedding cosine, or keyword overlap when no embedding)
to boost company-relevant news.

``source_path`` + ``file_hash`` drive incremental re-indexing: all chunks of
a file share the file's content hash, so an unchanged file is skipped.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from newsletter.core.db import Base


class ContextChunk(Base):
    """One chunk of an internal document, embedded for relevance scoring."""

    __tablename__ = "context_chunks"
    __table_args__ = (
        UniqueConstraint(
            "source_path", "chunk_index", name="uq_context_chunks_path_index"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_path: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (
            f"ContextChunk(id={self.id}, source_path={self.source_path!r}, "
            f"chunk_index={self.chunk_index})"
        )
```

- [ ] **Step 2: 모델 등록**

`src/newsletter/models/__init__.py` 에 import + `__all__` 추가:

```python
from newsletter.models.context_chunk import ContextChunk
```

`__all__` 리스트에 알파벳 순 위치(`CompanyInterest` 다음)에 `"ContextChunk",` 추가.

- [ ] **Step 3: 마이그레이션 자동 생성**

Run: `uv run alembic revision --autogenerate -m "add context_chunks table"`
Expected: `migrations/versions/<rev>_add_context_chunks_table.py` 생성. 출력에 `Detected added table 'context_chunks'`.

- [ ] **Step 4: 마이그레이션 내용 확인**

생성된 파일을 열어 `op.create_table("context_chunks", ...)` 와 `uq_context_chunks_path_index` 유니크 제약이 포함됐는지, 무관한 다른 테이블 변경이 섞이지 않았는지 확인한다. 무관 변경이 있으면 그 부분만 삭제한다.

- [ ] **Step 5: 마이그레이션 적용**

Run: `uv run alembic upgrade head`
Expected: 에러 없이 완료. `uv run alembic current` 가 새 revision을 head로 표시.

- [ ] **Step 6: 커밋**

```bash
git add src/newsletter/models/context_chunk.py src/newsletter/models/__init__.py migrations/versions/
git commit -m "feat(corpus): ContextChunk model + migration"
```

---

## Task 3: repository.py (청크 DB 함수)

**Files:**
- Create: `src/newsletter/slices/corpus/repository.py`
- Test: `tests/slices/corpus/test_repository.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/slices/corpus/test_repository.py`:

```python
"""corpus.repository — chunk persistence."""

from __future__ import annotations

from newsletter.slices.corpus import repository
from newsletter.slices.corpus.repository import ChunkInsert


def _insert(text: str, keywords: list[str]) -> ChunkInsert:
    return ChunkInsert(
        text=text, keywords=keywords, embedding=None, embedding_model=None
    )


def test_replace_file_chunks_inserts(db_session):
    n = repository.replace_file_chunks(
        db_session,
        source_path="a.md",
        file_hash="h1",
        chunks=[_insert("c0", ["x"]), _insert("c1", ["y"])],
    )
    db_session.commit()
    assert n == 2
    rows = repository.list_chunks(db_session)
    assert [r.chunk_index for r in rows] == [0, 1]
    assert {r.source_path for r in rows} == {"a.md"}


def test_replace_file_chunks_is_idempotent(db_session):
    repository.replace_file_chunks(
        db_session, source_path="a.md", file_hash="h1", chunks=[_insert("c0", [])]
    )
    db_session.commit()
    repository.replace_file_chunks(
        db_session, source_path="a.md", file_hash="h2", chunks=[_insert("new", [])]
    )
    db_session.commit()
    rows = repository.list_chunks(db_session)
    assert len(rows) == 1
    assert rows[0].text == "new"
    assert rows[0].file_hash == "h2"


def test_file_hashes_maps_path_to_hash(db_session):
    repository.replace_file_chunks(
        db_session, source_path="a.md", file_hash="h1",
        chunks=[_insert("c0", []), _insert("c1", [])],
    )
    repository.replace_file_chunks(
        db_session, source_path="b.txt", file_hash="h2", chunks=[_insert("c0", [])]
    )
    db_session.commit()
    assert repository.file_hashes(db_session) == {"a.md": "h1", "b.txt": "h2"}


def test_delete_all_returns_count(db_session):
    repository.replace_file_chunks(
        db_session, source_path="a.md", file_hash="h1",
        chunks=[_insert("c0", []), _insert("c1", [])],
    )
    db_session.commit()
    deleted = repository.delete_all(db_session)
    db_session.commit()
    assert deleted == 2
    assert repository.list_chunks(db_session) == []


def test_load_keywords_tolerates_bad_json(db_session):
    repository.replace_file_chunks(
        db_session, source_path="a.md", file_hash="h1",
        chunks=[_insert("c0", ["alpha", "beta"])],
    )
    db_session.commit()
    row = repository.list_chunks(db_session)[0]
    assert repository.load_keywords(row) == ["alpha", "beta"]
    row.keywords_json = "{not json"
    assert repository.load_keywords(row) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/slices/corpus/test_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.slices.corpus.repository`

- [ ] **Step 3: repository.py 구현**

`src/newsletter/slices/corpus/repository.py`:

```python
"""Data access for ContextChunk rows.

Pure functions over a SQLAlchemy session. Keywords are stored as JSON text;
the repository handles (de)serialization so callers deal in ``list[str]``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from newsletter.models.context_chunk import ContextChunk


@dataclass(frozen=True, slots=True)
class ChunkInsert:
    """One chunk to persist for a file."""

    text: str
    keywords: list[str]
    embedding: bytes | None
    embedding_model: str | None


def file_hashes(session: Session) -> dict[str, str]:
    """Return ``{source_path: file_hash}`` for incremental re-index checks."""
    rows = session.execute(
        select(ContextChunk.source_path, ContextChunk.file_hash)
    ).all()
    return {path: file_hash for path, file_hash in rows}


def replace_file_chunks(
    session: Session,
    *,
    source_path: str,
    file_hash: str,
    chunks: Sequence[ChunkInsert],
) -> int:
    """Delete a file's existing chunks, then insert the new set. Returns count."""
    session.execute(
        delete(ContextChunk).where(ContextChunk.source_path == source_path)
    )
    for index, chunk in enumerate(chunks):
        session.add(
            ContextChunk(
                source_path=source_path,
                file_hash=file_hash,
                chunk_index=index,
                text=chunk.text,
                keywords_json=_dump_keywords(chunk.keywords),
                embedding=chunk.embedding,
                embedding_model=chunk.embedding_model,
            )
        )
    session.flush()
    return len(chunks)


def list_chunks(session: Session) -> list[ContextChunk]:
    stmt = select(ContextChunk).order_by(
        ContextChunk.source_path, ContextChunk.chunk_index
    )
    return list(session.scalars(stmt).all())


def delete_all(session: Session) -> int:
    """Delete every chunk. Returns the number of rows removed."""
    rows = session.scalars(select(ContextChunk)).all()
    for row in rows:
        session.delete(row)
    session.flush()
    return len(rows)


def load_keywords(row: ContextChunk) -> list[str]:
    """Parse the JSON keywords column. Tolerant of malformed payloads."""
    try:
        parsed = json.loads(row.keywords_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(k) for k in parsed if k]


def _dump_keywords(keywords: Sequence[str]) -> str:
    cleaned = [k.strip() for k in keywords if k and k.strip()]
    return json.dumps(cleaned, ensure_ascii=False)


__all__ = [
    "ChunkInsert",
    "delete_all",
    "file_hashes",
    "list_chunks",
    "load_keywords",
    "replace_file_chunks",
]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/slices/corpus/test_repository.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/newsletter/slices/corpus/repository.py tests/slices/corpus/test_repository.py
git commit -m "feat(corpus): ContextChunk repository"
```

---

## Task 4: indexer.py (디렉터리 스캔 → 임베딩 → 영속화)

**Files:**
- Create: `src/newsletter/slices/corpus/schemas.py`
- Create: `src/newsletter/slices/corpus/indexer.py`
- Test: `tests/slices/corpus/test_indexer.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/slices/corpus/test_indexer.py`:

```python
"""corpus.indexer — scan a directory, chunk, embed, persist (incremental)."""

from __future__ import annotations

from pathlib import Path

from newsletter.core.embeddings import DisabledEmbeddingClient, deserialize
from newsletter.slices.corpus import repository
from newsletter.slices.corpus.indexer import index_corpus


class _FakeEmbed:
    model = "fake-embed"

    def embed(self, texts):
        # Deterministic non-zero vector per text.
        return [[float(len(t)), 1.0, 0.0, 0.0] for t in texts]


def _write(root: Path, name: str, body: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_index_scans_and_persists_chunks(tmp_path, db_session):
    _write(tmp_path, "doc.md", "# 제목\n첫 문단.\n\n## 둘\n둘째 문단.")
    report = index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    db_session.commit()
    assert report.scanned == 1
    assert report.indexed == 1
    assert report.skipped == 0
    assert report.chunks == 2
    assert report.embedded == 2
    rows = repository.list_chunks(db_session)
    assert len(rows) == 2
    assert deserialize(rows[0].embedding)  # non-empty vector
    assert rows[0].embedding_model == "fake-embed"


def test_index_skips_unchanged_files(tmp_path, db_session):
    _write(tmp_path, "doc.md", "# 제목\n내용.")
    index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    db_session.commit()
    report = index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    db_session.commit()
    assert report.skipped == 1
    assert report.indexed == 0


def test_index_reindexes_changed_file(tmp_path, db_session):
    _write(tmp_path, "doc.md", "# 제목\n옛 내용.")
    index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    db_session.commit()
    _write(tmp_path, "doc.md", "# 제목\n새 내용 완전히 다름.")
    report = index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    db_session.commit()
    assert report.indexed == 1
    assert report.skipped == 0
    rows = repository.list_chunks(db_session)
    assert "새 내용" in rows[0].text


def test_index_without_embeddings_stores_keywords_only(tmp_path, db_session):
    _write(tmp_path, "doc.md", "rag agent vector store retrieval")
    report = index_corpus(
        db_session, root=tmp_path, embed_client=DisabledEmbeddingClient()
    )
    db_session.commit()
    assert report.embedded == 0
    row = repository.list_chunks(db_session)[0]
    assert row.embedding is None
    assert "rag" in repository.load_keywords(row)


def test_index_empty_directory(tmp_path, db_session):
    report = index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    assert report.scanned == 0
    assert report.indexed == 0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/slices/corpus/test_indexer.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.slices.corpus.indexer`

- [ ] **Step 3: schemas.py 구현**

`src/newsletter/slices/corpus/schemas.py`:

```python
"""Output shapes for the corpus slice."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class IndexReport:
    """Summary of one ``index_corpus`` run."""

    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    chunks: int = 0
    embedded: int = 0


__all__ = ["IndexReport"]
```

- [ ] **Step 4: indexer.py 구현**

`src/newsletter/slices/corpus/indexer.py`:

```python
"""Index a company-context directory into ContextChunk rows.

Incremental: each file's content hash is compared against the stored hash;
unchanged files are skipped. Changed/new files are re-chunked, embedded in a
single batch call, and persisted via ``replace_file_chunks``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from newsletter.core.embeddings import EmbeddingClient, serialize
from newsletter.core.logging import get_logger
from newsletter.slices.corpus import repository
from newsletter.slices.corpus.chunking import chunk_text, extract_keywords
from newsletter.slices.corpus.repository import ChunkInsert
from newsletter.slices.corpus.schemas import IndexReport

log = get_logger(__name__)

_SUFFIXES = {".md", ".txt"}


def index_corpus(
    session: Session, *, root: Path, embed_client: EmbeddingClient
) -> IndexReport:
    """Scan ``root`` recursively and (re)index changed Markdown/text files."""
    report = IndexReport()
    stored = repository.file_hashes(session)

    files = sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _SUFFIXES
    )
    for path in files:
        report.scanned += 1
        rel = path.relative_to(root).as_posix()
        content = path.read_text(encoding="utf-8")
        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        if stored.get(rel) == file_hash:
            report.skipped += 1
            continue

        texts = chunk_text(content)
        inserts = _build_inserts(texts, embed_client)
        written = repository.replace_file_chunks(
            session, source_path=rel, file_hash=file_hash, chunks=inserts
        )
        report.indexed += 1
        report.chunks += written
        report.embedded += sum(1 for c in inserts if c.embedding is not None)

    log.info(
        "corpus.indexed",
        scanned=report.scanned,
        indexed=report.indexed,
        skipped=report.skipped,
        chunks=report.chunks,
        embedded=report.embedded,
    )
    return report


def _build_inserts(
    texts: list[str], embed_client: EmbeddingClient
) -> list[ChunkInsert]:
    if not texts:
        return []
    vectors = embed_client.embed(texts)
    model = getattr(embed_client, "model", None)
    inserts: list[ChunkInsert] = []
    for index, text in enumerate(texts):
        has_vector = bool(vectors) and index < len(vectors)
        embedding = serialize(vectors[index]) if has_vector else None
        inserts.append(
            ChunkInsert(
                text=text,
                keywords=extract_keywords(text),
                embedding=embedding,
                embedding_model=model if embedding is not None else None,
            )
        )
    return inserts


__all__ = ["index_corpus"]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/slices/corpus/test_indexer.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: 커밋**

```bash
git add src/newsletter/slices/corpus/schemas.py src/newsletter/slices/corpus/indexer.py tests/slices/corpus/test_indexer.py
git commit -m "feat(corpus): incremental directory indexer"
```

---

## Task 5: scoring — corpus_relevance_factor + score_items 인자

**Files:**
- Modify: `src/newsletter/slices/integration/scoring.py`
- Test: `tests/slices/integration/test_scoring_corpus.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/slices/integration/test_scoring_corpus.py`:

```python
"""scoring.corpus_relevance_factor — company-document relevance boost."""

from __future__ import annotations

from datetime import UTC, datetime

from newsletter.slices.integration.scoring import (
    CorpusChunk,
    ScoreInput,
    corpus_relevance_factor,
    score_items,
)

_NOW = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)


def test_no_chunks_returns_neutral():
    factor = corpus_relevance_factor(
        title="anything", summary=None, item_embedding=None, chunks=[]
    )
    assert factor == 1.0


def test_keyword_fallback_boosts_on_overlap():
    chunks = [CorpusChunk(keywords=("rag", "agent", "vector"), embedding=None)]
    factor = corpus_relevance_factor(
        title="New RAG agent vector pipeline",
        summary=None,
        item_embedding=None,
        chunks=chunks,
    )
    # 3 distinct hits == saturation -> full strength -> 1.0 + 1.0 * 0.3
    assert factor == 1.3


def test_keyword_fallback_partial_overlap():
    chunks = [CorpusChunk(keywords=("rag", "agent", "vector"), embedding=None)]
    factor = corpus_relevance_factor(
        title="A RAG note", summary=None, item_embedding=None, chunks=chunks
    )
    # 1 hit / saturation(3) -> strength 1/3
    assert abs(factor - (1.0 + (1 / 3) * 0.3)) < 1e-9


def test_embedding_path_scales_with_cosine():
    chunks = [CorpusChunk(keywords=(), embedding=[1.0, 0.0, 0.0])]
    factor = corpus_relevance_factor(
        title="x", summary=None, item_embedding=[1.0, 0.0, 0.0], chunks=chunks
    )
    # cosine 1.0 -> strength 1.0 -> cap clamp 1.3
    assert factor == 1.3


def test_embedding_below_threshold_is_neutral():
    chunks = [CorpusChunk(keywords=(), embedding=[0.0, 1.0, 0.0])]
    factor = corpus_relevance_factor(
        title="x", summary=None, item_embedding=[1.0, 0.0, 0.0], chunks=chunks
    )
    assert factor == 1.0


def test_score_items_applies_corpus_boost():
    item = ScoreInput(
        id=1,
        trust_level="media",
        published_at=_NOW,
        title="RAG agent vector",
        summary=None,
        source_name="src",
    )
    chunks = [CorpusChunk(keywords=("rag", "agent", "vector"), embedding=None)]
    base = score_items([item], llm=None, now=_NOW)
    boosted = score_items([item], llm=None, now=_NOW, corpus_chunks=chunks)
    assert boosted[1] > base[1]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/slices/integration/test_scoring_corpus.py -v`
Expected: FAIL — `ImportError: cannot import name 'CorpusChunk'`

- [ ] **Step 3: scoring.py 수정 — CorpusChunk + 상수 추가**

`src/newsletter/slices/integration/scoring.py`, `InterestProfile` dataclass 정의 바로 뒤에 추가:

```python
@dataclass(slots=True, frozen=True)
class CorpusChunk:
    """One company-document chunk materialized for relevance scoring.

    ``keywords`` is lowercased so callers match against pre-lowercased text.
    """

    keywords: tuple[str, ...]
    embedding: Sequence[float] | None
```

기존 interest 튜닝 상수(`_INTEREST_COSINE_THRESHOLD = 0.55`) 아래에 추가:

```python
# Corpus (company-document) relevance tuning. Capped lower than interests
# because both boosts compound on the base score.
_CORPUS_CAP: Final[float] = 0.3
_CORPUS_COSINE_THRESHOLD: Final[float] = 0.55
_CORPUS_KEYWORD_SATURATION: Final[int] = 3
```

- [ ] **Step 4: scoring.py 수정 — corpus_relevance_factor 추가**

`interest_match_factor` 함수와 그 헬퍼 `_has_any_keyword` 뒤에 추가:

```python
def corpus_relevance_factor(
    *,
    title: str,
    summary: str | None,
    item_embedding: Sequence[float] | None,
    chunks: list[CorpusChunk],
) -> float:
    """Return a multiplier in [1.0, 1.0 + _CORPUS_CAP] from corpus relevance.

    Prefers the embedding path (max cosine over embedded chunks). When the
    item has no embedding or no chunk is embedded, falls back to counting
    distinct corpus keywords present in the item text.
    """
    if not chunks:
        return 1.0

    embedded = [c.embedding for c in chunks if c.embedding is not None]
    if item_embedding is not None and embedded:
        best = max(cosine(item_embedding, vec) for vec in embedded)
        if best < _CORPUS_COSINE_THRESHOLD:
            return 1.0
        strength = (best - _CORPUS_COSINE_THRESHOLD) / (
            1.0 - _CORPUS_COSINE_THRESHOLD
        )
    else:
        text = (title + " " + (summary or "")).lower()
        keywords = {kw for chunk in chunks for kw in chunk.keywords if kw}
        hits = sum(1 for kw in keywords if kw in text)
        if hits == 0:
            return 1.0
        strength = min(1.0, hits / _CORPUS_KEYWORD_SATURATION)

    return 1.0 + strength * _CORPUS_CAP
```

- [ ] **Step 5: scoring.py 수정 — score_items 인자 + 합성**

`score_items` 시그니처에 인자 추가 (기존 `item_embeddings` 파라미터 다음 줄):

```python
    corpus_chunks: list[CorpusChunk] | None = None,
```

함수 본문의 `interest_list = interests or []` 다음에 추가:

```python
    corpus_list = corpus_chunks or []
```

`base = { ... }` dict comprehension을 다음으로 교체 (interest factor 뒤에 corpus factor 곱셈 추가):

```python
    base = {
        item.id: base_importance(item.trust_level, item.published_at, now, half_life_days)
        * interest_match_factor(
            title=item.title,
            summary=item.summary,
            item_embedding=embeddings_by_id.get(item.id),
            interests=interest_list,
        )
        * corpus_relevance_factor(
            title=item.title,
            summary=item.summary,
            item_embedding=embeddings_by_id.get(item.id),
            chunks=corpus_list,
        )
        for item in items
    }
```

`__all__` 리스트에 `"CorpusChunk"` 와 `"corpus_relevance_factor"` 추가.

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest tests/slices/integration/test_scoring_corpus.py tests/slices/integration/test_scoring.py tests/slices/integration/test_scoring_interests.py -v`
Expected: PASS (전체 — 신규 6개 + 기존 회귀 없음)

- [ ] **Step 7: 커밋**

```bash
git add src/newsletter/slices/integration/scoring.py tests/slices/integration/test_scoring_corpus.py
git commit -m "feat(scoring): corpus relevance factor compounding on base score"
```

---

## Task 6: 통합 서비스 — corpus chunk 로드 + 전달

**Files:**
- Modify: `src/newsletter/slices/integration/service.py`
- Test: `tests/slices/integration/test_service_corpus.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/slices/integration/test_service_corpus.py`:

```python
"""integrate(): corpus chunks boost matching items' importance."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.corpus import repository as corpus_repo
from newsletter.slices.corpus.repository import ChunkInsert
from newsletter.slices.integration.service import integrate
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

_NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


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


def _seed_item(db_session: Session, *, title: str) -> int:
    raw = RawItem(
        source_id="src",
        title=title,
        url=f"https://example.com/{title[:24]}",
        published_at=_NOW,
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
        importance_score=0.0,
        summary=title,
        keywords=None,
        duplicate_group_id=None,
    )
    db_session.add(proc)
    db_session.flush()
    return proc.id


def _final_score(db_session: Session, proc_id: int) -> float:
    return float(
        db_session.scalars(
            select(ProcessedItem.importance_score).where(ProcessedItem.id == proc_id)
        ).one()
    )


def test_corpus_chunk_boosts_matching_item(db_session: Session) -> None:
    _seed_source(db_session)
    matched = _seed_item(db_session, title="RAG agent vector pipeline")
    other = _seed_item(db_session, title="Bitcoin price update today")
    db_session.commit()

    integrate(db_session, now=_NOW)
    db_session.commit()
    base_matched = _final_score(db_session, matched)
    base_other = _final_score(db_session, other)

    corpus_repo.replace_file_chunks(
        db_session,
        source_path="company/focus.md",
        file_hash="h1",
        chunks=[
            ChunkInsert(
                text="우리는 rag agent vector 에 집중한다",
                keywords=["rag", "agent", "vector"],
                embedding=None,
                embedding_model=None,
            )
        ],
    )
    db_session.commit()

    integrate(db_session, now=_NOW)
    db_session.commit()
    assert _final_score(db_session, matched) > base_matched
    assert _final_score(db_session, other) == base_other


def test_no_chunks_leaves_scores_unchanged(db_session: Session) -> None:
    _seed_source(db_session)
    item = _seed_item(db_session, title="RAG agent vector")
    db_session.commit()
    integrate(db_session, now=_NOW)
    db_session.commit()
    before = _final_score(db_session, item)

    integrate(db_session, now=_NOW)
    db_session.commit()
    assert _final_score(db_session, item) == before
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/slices/integration/test_service_corpus.py -v`
Expected: FAIL — `test_corpus_chunk_boosts_matching_item` 에서 boost 미적용으로 assert 실패.

- [ ] **Step 3: service.py 수정 — import 추가**

`src/newsletter/slices/integration/service.py` 상단 import 영역에서:

scoring import 블록에 `CorpusChunk` 추가:

```python
from newsletter.slices.integration.scoring import (
    CorpusChunk,
    InterestProfile,
    ScoreInput,
    score_items,
)
```

interests import 아래에 corpus repository import 추가:

```python
from newsletter.slices.corpus import repository as corpus_repo
from newsletter.slices.interests import repository as interests_repo
```

- [ ] **Step 4: service.py 수정 — chunk 로드 + score_items 전달**

`interests = _load_interests(session)` 다음 줄에 추가:

```python
    corpus_chunks = _load_corpus_chunks(session)
```

`score_items(...)` 호출에 인자 추가 (`item_embeddings=...` 다음):

```python
        corpus_chunks=corpus_chunks,
```

`log.info("integration.done", ...)` 호출에 필드 추가:

```python
        corpus_chunks=len(corpus_chunks),
```

`_load_interests` 함수 정의 바로 아래에 새 함수 추가:

```python
def _load_corpus_chunks(session: Session) -> list[CorpusChunk]:
    """Materialize ContextChunk rows into score-side corpus chunks."""
    rows = corpus_repo.list_chunks(session)
    chunks: list[CorpusChunk] = []
    for row in rows:
        keywords = tuple(k.lower() for k in corpus_repo.load_keywords(row))
        embedding = deserialize(row.embedding) if row.embedding else None
        chunks.append(CorpusChunk(keywords=keywords, embedding=embedding))
    return chunks
```

(`deserialize` 는 이미 service.py 상단에서 import됨.)

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/slices/integration/test_service_corpus.py tests/slices/integration/test_service_interests.py tests/slices/integration/test_service.py -v`
Expected: PASS (신규 2개 + 기존 회귀 없음)

- [ ] **Step 6: 커밋**

```bash
git add src/newsletter/slices/integration/service.py tests/slices/integration/test_service_corpus.py
git commit -m "feat(integration): load corpus chunks into scoring pass"
```

---

## Task 7: CLI — newsletter corpus index/list/clear/status

**Files:**
- Create: `src/newsletter/slices/corpus/cli.py`
- Modify: `src/newsletter/cli.py`
- Test: `tests/slices/corpus/test_cli.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/slices/corpus/test_cli.py`:

```python
"""corpus CLI smoke tests."""

from __future__ import annotations

from typer.testing import CliRunner

from newsletter.slices.corpus import repository
from newsletter.slices.corpus.cli import app

runner = CliRunner()


def test_index_without_dir_configured_warns(db_session, monkeypatch):
    monkeypatch.setenv("COMPANY_CONTEXT_DIR", "")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()
    result = runner.invoke(app, ["index"])
    assert result.exit_code == 0
    assert "COMPANY_CONTEXT_DIR" in result.output


def test_index_indexes_directory(tmp_path, db_session, monkeypatch):
    (tmp_path / "doc.md").write_text("# 제목\nrag agent 내용", encoding="utf-8")
    monkeypatch.setenv("COMPANY_CONTEXT_DIR", str(tmp_path))
    # No embedding key -> DisabledEmbeddingClient (never hits the real API).
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()
    result = runner.invoke(app, ["index"])
    assert result.exit_code == 0, result.output
    db_session.expire_all()
    assert len(repository.list_chunks(db_session)) >= 1


def test_clear_removes_chunks(db_session, monkeypatch):
    from newsletter.slices.corpus.repository import ChunkInsert

    repository.replace_file_chunks(
        db_session, source_path="a.md", file_hash="h1",
        chunks=[ChunkInsert(text="c", keywords=[], embedding=None, embedding_model=None)],
    )
    db_session.commit()
    result = runner.invoke(app, ["clear"])
    assert result.exit_code == 0
    db_session.expire_all()
    assert repository.list_chunks(db_session) == []


def test_list_empty(db_session):
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "no chunks" in result.output.lower()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/slices/corpus/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: newsletter.slices.corpus.cli`

- [ ] **Step 3: cli.py 구현**

`src/newsletter/slices/corpus/cli.py`:

```python
"""``newsletter corpus`` — index internal company documents for scoring.

``corpus index`` scans ``COMPANY_CONTEXT_DIR`` and (re)indexes changed files.
When ``VOYAGE_API_KEY`` is unset, chunks store keywords only and the importance
boost falls back to keyword overlap.
"""

from __future__ import annotations

from pathlib import Path

import typer

from newsletter.core.config import get_settings
from newsletter.core.db import session_scope
from newsletter.slices.corpus import repository
from newsletter.slices.corpus.indexer import index_corpus
from newsletter.slices.monitoring.recorder import build_embedding_client

app = typer.Typer(
    help="Index internal company documents that boost importance scoring.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command("index")
def cmd_index() -> None:
    """Scan COMPANY_CONTEXT_DIR and (re)index changed documents."""
    settings = get_settings()
    if not settings.company_context_dir:
        typer.echo(
            "COMPANY_CONTEXT_DIR 가 설정되지 않았습니다. 인덱싱을 건너뜁니다.",
            err=True,
        )
        return
    root = Path(settings.company_context_dir)
    if not root.is_dir():
        typer.echo(f"디렉터리가 없습니다: {root}", err=True)
        raise typer.Exit(code=1)

    client = build_embedding_client()
    with session_scope() as session:
        report = index_corpus(session, root=root, embed_client=client)
    typer.echo(
        f"corpus index 완료: scanned={report.scanned} indexed={report.indexed} "
        f"skipped={report.skipped} chunks={report.chunks} embedded={report.embedded}"
    )


@app.command("list")
def cmd_list() -> None:
    """Show indexed chunks grouped by file."""
    with session_scope() as session:
        rows = repository.list_chunks(session)
    if not rows:
        typer.echo("(no chunks indexed)")
        return
    by_file: dict[str, list] = {}
    for row in rows:
        by_file.setdefault(row.source_path, []).append(row)
    typer.echo(f"{'chunks':>7} {'embed':>5}  file")
    typer.echo("-" * 40)
    for path, chunks in sorted(by_file.items()):
        embedded = sum(1 for c in chunks if c.embedding is not None)
        typer.echo(f"{len(chunks):>7} {embedded:>5}  {path}")


@app.command("clear")
def cmd_clear() -> None:
    """Delete every indexed chunk. Irreversible."""
    with session_scope() as session:
        deleted = repository.delete_all(session)
    typer.echo(f"corpus clear 완료: {deleted} chunks 삭제")


@app.command("status")
def cmd_status() -> None:
    """Compare COMPANY_CONTEXT_DIR against the indexed state."""
    settings = get_settings()
    has_key = bool(settings.voyage_api_key)
    typer.echo(f"embedding key: {'있음' if has_key else '없음 (키워드 폴백)'}")
    if not settings.company_context_dir:
        typer.echo("COMPANY_CONTEXT_DIR: (미설정)")
        return
    root = Path(settings.company_context_dir)
    typer.echo(f"COMPANY_CONTEXT_DIR: {root}")
    with session_scope() as session:
        stored = repository.file_hashes(session)
    typer.echo(f"indexed files: {len(stored)}")
```

- [ ] **Step 4: 루트 CLI 등록**

`src/newsletter/cli.py` 의 import 영역(다른 슬라이스 cli import와 같은 곳)에 추가:

```python
from newsletter.slices.corpus.cli import app as corpus_app  # noqa: E402
```

`app.add_typer(interests_app, name="interests")` 다음 줄에 추가:

```python
app.add_typer(corpus_app, name="corpus")
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/slices/corpus/test_cli.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: 커밋**

```bash
git add src/newsletter/slices/corpus/cli.py src/newsletter/cli.py tests/slices/corpus/test_cli.py
git commit -m "feat(corpus): CLI (index/list/clear/status) + root registration"
```

---

## Task 8: 설정 + 문서 (config / .env.example / AGENTS.md)

**Files:**
- Modify: `src/newsletter/core/config.py`
- Modify: `.env.example`
- Modify: `AGENTS.md`

- [ ] **Step 1: config.py 에 설정 추가**

`src/newsletter/core/config.py`, Notion 설정 블록 근처(Phase 2/3 설정 영역)에 추가:

```python
    # 회사 관심사 RAG (Phase 3) — 사내 문서 코퍼스 디렉터리. 빈 값이면 기능 off.
    company_context_dir: str = Field(
        default="",
        description="Directory of internal .md/.txt docs indexed for scoring.",
    )
```

- [ ] **Step 2: 설정 로딩 확인 (기존 테스트로 회귀 확인)**

Run: `uv run pytest tests/ -k config -v`
Expected: PASS (설정 관련 테스트 회귀 없음). config 전용 테스트가 없으면 이 단계는 `uv run python -c "from newsletter.core.config import Settings; print(Settings().company_context_dir == '')"` 로 대체하고 `True` 출력 확인.

- [ ] **Step 3: .env.example 갱신**

`.env.example` 의 Voyage/Notion 설정 근처에 추가:

```bash
# 회사 관심사 RAG — 사내 문서(.md/.txt) 디렉터리. 비워두면 기능 비활성.
COMPANY_CONTEXT_DIR=docs/company
```

- [ ] **Step 4: AGENTS.md 갱신**

`AGENTS.md` 에 corpus 슬라이스를 다른 슬라이스와 동일 형식으로 추가:
- 슬라이스 목록/디렉터리 설명에 `corpus`(사내 문서 인덱싱 → 스코어링 보강) 한 줄.
- CLI 명령 목록에 `newsletter corpus index/list/clear/status` 추가.
- 설정 표/목록에 `COMPANY_CONTEXT_DIR` 추가.

(기존 문서의 표기 형식을 그대로 따른다. 새 형식을 만들지 않는다.)

- [ ] **Step 5: 전체 테스트 + 린트**

Run: `uv run pytest`
Expected: PASS (전체 — 기존 502개 + 신규 약 25개).

Run: `uv run ruff check src/newsletter/slices/corpus src/newsletter/slices/integration/scoring.py src/newsletter/slices/integration/service.py src/newsletter/core/config.py src/newsletter/cli.py`
Expected: 통과. (전역 `ruff format` 은 핸드오프 노트의 드리프트 주의에 따라 돌리지 않는다 — 신규/수정 파일만 `ruff check --fix`.)

- [ ] **Step 6: 커밋**

```bash
git add src/newsletter/core/config.py .env.example AGENTS.md
git commit -m "feat(corpus): COMPANY_CONTEXT_DIR setting + docs"
```

---

## 검증 체크리스트 (전체 완료 후)

- [ ] `uv run pytest` 전부 통과.
- [ ] `uv run alembic upgrade head` 적용 완료, `context_chunks` 테이블 존재.
- [ ] `COMPANY_CONTEXT_DIR` 미설정 시 `newsletter corpus index` 가 경고 후 no-op.
- [ ] 청크 0개일 때 `integrate` 결과가 corpus 도입 전과 동일(회귀 0).
- [ ] 신규/수정 파일 `ruff check` 통과.
- [ ] 핸드오프 노트(`hitl/`) 갱신 — Phase 3 첫 항목 완료 기록.
```
