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
    _seed_item(
        db_session,
        title="신규 고객 매출 분석",
        summary="영업 성과",
        published_at=datetime(2026, 5, 20, 9, 0),
    )
    _seed_item(
        db_session,
        title="코드 리뷰 개발 도구",
        summary="엔지니어링 생산성",
        published_at=datetime(2026, 5, 20, 10, 0),
    )
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
        db_session,
        title="aligned",
        summary="x",
        published_at=datetime(2026, 5, 20, 9, 0),
        embedding=serialize([1.0, 0.0]),
    )
    _seed_item(
        db_session,
        title="orthogonal",
        summary="y",
        published_at=datetime(2026, 5, 20, 10, 0),
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
        _seed_item(
            db_session,
            title=f"고객 사례 {i}",
            summary="x",
            published_at=datetime(2026, 5, 20, 9, i),
        )
    _seed_item(
        db_session,
        title="무관한 기사",
        summary="배포 파이프라인",
        published_at=datetime(2026, 5, 20, 9, 30),
    )
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


def test_item_attributed_to_multiple_departments(db_session: Session):
    # One item relevant to two departments (shared token) appears under both.
    _seed_source(db_session)
    repository.add(db_session, DepartmentCreate(name="영업", description="고객"))
    repository.add(db_session, DepartmentCreate(name="마케팅", description="고객"))
    _seed_item(db_session, title="고객 분석", summary="x", published_at=datetime(2026, 5, 20, 9, 0))
    db_session.commit()
    digest = build_department_digest(
        db_session, days=7, until=_UNTIL, embed_client=DisabledEmbeddingClient()
    )
    by_name = {e.name: e for e in digest.departments}
    assert by_name["영업"].headlines[0].title == "고객 분석"
    assert by_name["마케팅"].headlines[0].title == "고객 분석"


def test_embedding_mode_with_one_empty_department_vector(db_session: Session):
    # Embedding mode where one department's vector is empty: indexing stays
    # aligned, the empty-vector department yields no headlines (score 0).
    _seed_source(db_session)
    repository.add(db_session, DepartmentCreate(name="A", description="alpha"))
    repository.add(db_session, DepartmentCreate(name="B", description="beta"))
    _seed_item(
        db_session,
        title="aligned",
        summary="x",
        published_at=datetime(2026, 5, 20, 9, 0),
        embedding=serialize([1.0, 0.0]),
    )
    db_session.commit()
    # A gets a real vector, B gets an empty vector
    digest = build_department_digest(
        db_session, days=7, until=_UNTIL, embed_client=_FakeEmbed([[1.0, 0.0], []])
    )
    assert digest.mode == "embedding"  # any() is True because A's vector is non-empty
    by_name = {e.name: e for e in digest.departments}
    assert [h.title for h in by_name["A"].headlines] == ["aligned"]
    assert by_name["B"].headlines == []  # empty dept vector -> cosine 0 -> excluded
