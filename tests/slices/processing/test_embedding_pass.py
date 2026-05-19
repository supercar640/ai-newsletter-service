"""processing.service: embedding generation on the processed batch."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.core.embeddings import DisabledEmbeddingClient, deserialize
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.processing.service import process
from newsletter.slices.sources import repository
from newsletter.slices.sources.schemas import SourceCreate


def _seed(db_session: Session) -> None:
    repository.add(
        db_session,
        SourceCreate(
            source_id="src",
            name="src",
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
        ),
    )
    for i in range(3):
        db_session.add(
            RawItem(
                source_id="src",
                title=f"OpenAI announces GPT-{i}",
                url=f"https://example.com/{i}",
                published_at=datetime(2025, 5, 12, tzinfo=UTC),
                raw_summary="Some AI summary.",
                language="en",
            )
        )
    db_session.commit()


class _StubEmbeddingClient:
    """Deterministic stand-in: returns a unit vector indexed by position."""

    model = "stub-embed"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return [[float(i + 1), 0.0, 0.0] for i in range(len(texts))]


def test_process_populates_embedding_when_client_provided(db_session: Session) -> None:
    _seed(db_session)
    client = _StubEmbeddingClient()

    process(db_session, keyword_only=True, embedding_client=client)
    db_session.commit()

    rows = list(db_session.scalars(select(ProcessedItem)).all())
    assert len(rows) == 3
    for row in rows:
        assert row.embedding is not None
        assert row.embedding_model == "stub-embed"
        vec = deserialize(row.embedding)
        assert len(vec) == 3
    # One batched call rather than three.
    assert len(client.calls) == 1
    assert len(client.calls[0]) == 3


def test_process_leaves_embedding_null_when_disabled(db_session: Session) -> None:
    _seed(db_session)
    process(db_session, keyword_only=True, embedding_client=DisabledEmbeddingClient())
    db_session.commit()
    rows = list(db_session.scalars(select(ProcessedItem)).all())
    assert rows
    assert all(r.embedding is None for r in rows)
    assert all(r.embedding_model is None for r in rows)


def test_process_no_embedding_client_means_null(db_session: Session) -> None:
    _seed(db_session)
    process(db_session, keyword_only=True)
    db_session.commit()
    rows = list(db_session.scalars(select(ProcessedItem)).all())
    assert all(r.embedding is None for r in rows)


def test_process_continues_when_embedding_provider_fails(
    db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    _seed(db_session)

    class _Failing:
        model = "x"

        def embed(self, texts):
            raise RuntimeError("network error")

    process(db_session, keyword_only=True, embedding_client=_Failing())
    db_session.commit()
    rows = list(db_session.scalars(select(ProcessedItem)).all())
    # Rows persist; embedding stays NULL. Pipeline must not block on embed failure.
    assert len(rows) == 3
    assert all(r.embedding is None for r in rows)
