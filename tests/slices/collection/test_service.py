"""End-to-end-ish tests for ``collect_all`` using fake collectors."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source
from newsletter.slices.collection.base import (
    Collector,
    CollectorError,
    CollectorResult,
    UnsupportedSourceTypeError,
)
from newsletter.slices.collection.service import collect_all
from newsletter.slices.sources import repository
from newsletter.slices.sources.schemas import SourceCreate


class _FakeCollector:
    def __init__(self, items: list[CollectorResult]) -> None:
        self._items = items

    def collect(self, source: Source) -> list[CollectorResult]:
        return list(self._items)


class _FailingCollector:
    def collect(self, source: Source) -> list[CollectorResult]:
        raise CollectorError("boom")


def _factory(mapping: dict[str, Collector]):
    def factory(source_type: str) -> Collector:
        try:
            return mapping[source_type]
        except KeyError as exc:
            raise UnsupportedSourceTypeError(source_type) from exc

    return factory


def _add_source(
    db_session: Session,
    source_id: str,
    *,
    type_: str = "RSS",
    track: str = "expert_news",
    enabled: bool = True,
) -> Source:
    src = repository.add(
        db_session,
        SourceCreate(
            source_id=source_id,
            name=source_id,
            type=type_,  # type: ignore[arg-type]
            content_track=track,  # type: ignore[arg-type]
            endpoint="https://example.com",
            language="en",
        ),
    )
    if not enabled:
        repository.disable(db_session, source_id)
    return src


def _item(url: str, *, title: str = "t", summary: str = "s") -> CollectorResult:
    return CollectorResult(
        title=title,
        url=url,
        published_at=datetime(2025, 5, 12, tzinfo=UTC),
        raw_summary=summary,
    )


def test_collect_all_inserts_new_items(db_session: Session) -> None:
    _add_source(db_session, "a")
    db_session.commit()

    items = [_item("https://example.com/a1"), _item("https://example.com/a2")]
    report = collect_all(
        db_session,
        collector_factory=_factory({"RSS": _FakeCollector(items)}),
    )
    db_session.commit()

    assert report.total_fetched == 2
    assert report.total_inserted == 2
    rows = db_session.scalars(select(RawItem)).all()
    assert {r.url for r in rows} == {"https://example.com/a1", "https://example.com/a2"}


def test_collect_all_dedupes_within_batch(db_session: Session) -> None:
    _add_source(db_session, "a")
    db_session.commit()

    items = [_item("https://example.com/dup"), _item("https://example.com/dup")]
    report = collect_all(
        db_session,
        collector_factory=_factory({"RSS": _FakeCollector(items)}),
    )
    db_session.commit()

    assert report.total_fetched == 2
    assert report.total_inserted == 1
    assert report.total_duplicates == 1


def test_collect_all_dedupes_against_existing_rows(db_session: Session) -> None:
    _add_source(db_session, "a")
    db_session.commit()

    factory = _factory({"RSS": _FakeCollector([_item("https://example.com/persist")])})
    collect_all(db_session, collector_factory=factory)
    db_session.commit()

    report = collect_all(db_session, collector_factory=factory)
    db_session.commit()
    assert report.total_inserted == 0
    assert report.total_duplicates == 1


def test_collect_all_skips_disabled_sources(db_session: Session) -> None:
    _add_source(db_session, "off", enabled=True)
    repository.disable(db_session, "off")
    db_session.commit()

    report = collect_all(
        db_session,
        collector_factory=_factory({"RSS": _FakeCollector([_item("https://x")])}),
    )
    db_session.commit()
    assert report.per_source == []
    assert report.total_inserted == 0


def test_collect_all_respects_source_id_filter(db_session: Session) -> None:
    _add_source(db_session, "a")
    _add_source(db_session, "b")
    db_session.commit()

    factory = _factory({"RSS": _FakeCollector([_item("https://example.com/x")])})
    report = collect_all(db_session, source_ids=["a"], collector_factory=factory)
    db_session.commit()

    assert [s.source_id for s in report.per_source] == ["a"]
    assert report.total_inserted == 1


def test_collect_all_records_collector_error(db_session: Session) -> None:
    _add_source(db_session, "a")
    db_session.commit()

    report = collect_all(
        db_session,
        collector_factory=_factory({"RSS": _FailingCollector()}),
    )

    assert len(report.errors) == 1
    assert report.errors[0].source_id == "a"
    assert "boom" in (report.errors[0].error or "")
    assert report.total_inserted == 0


def test_collect_all_marks_unsupported(db_session: Session) -> None:
    _add_source(db_session, "a", type_="RSS")
    db_session.commit()

    # Empty factory -> any type is unsupported.
    report = collect_all(db_session, collector_factory=_factory({}))

    assert len(report.per_source) == 1
    assert report.per_source[0].error is not None
    assert "unsupported" in (report.per_source[0].error or "")
