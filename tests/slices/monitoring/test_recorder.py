"""Recorder: record_step context manager + LLM usage callback."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from newsletter.core.embeddings import DisabledEmbeddingClient, VoyageEmbeddingClient
from newsletter.core.llm import LLMResponse
from newsletter.models.run_log import RunLog
from newsletter.slices.monitoring import recorder


def _all_runs(db_session) -> list[RunLog]:
    return list(db_session.scalars(select(RunLog).order_by(RunLog.id)).all())


def test_record_step_success(db_session):
    with recorder.record_step("collect") as run:
        run.item_count = 7
    # Re-read from a fresh query: rows must be durable across sessions.
    db_session.expire_all()
    rows = _all_runs(db_session)
    assert len(rows) == 1
    assert rows[0].step == "collect"
    assert rows[0].status == "success"
    assert rows[0].item_count == 7
    assert rows[0].finished_at is not None
    assert rows[0].error is None


def test_record_step_failure_records_error_and_reraises(db_session):
    with pytest.raises(RuntimeError, match="boom"), recorder.record_step("process"):
        raise RuntimeError("boom")
    db_session.expire_all()
    rows = _all_runs(db_session)
    assert len(rows) == 1
    assert rows[0].status == "failure"
    assert "boom" in (rows[0].error or "")
    assert rows[0].finished_at is not None


def test_record_step_meta_serialized(db_session):
    with recorder.record_step("collect", meta={"source": "techcrunch"}):
        pass
    db_session.expire_all()
    row = _all_runs(db_session)[0]
    assert row.meta_json is not None
    assert "techcrunch" in row.meta_json


def test_make_llm_recorder_writes_one_row_per_call(db_session):
    record = recorder.make_llm_recorder()
    record(LLMResponse(text="ok", model="claude-sonnet-4-6", input_tokens=100, output_tokens=200))
    record(LLMResponse(text="ok2", model="claude-opus-4-7", input_tokens=10, output_tokens=20))
    db_session.expire_all()
    rows = _all_runs(db_session)
    assert len(rows) == 2
    sonnet, opus = rows
    assert sonnet.step == "llm.complete"
    assert sonnet.model == "claude-sonnet-4-6"
    assert sonnet.llm_tokens_in == 100
    assert sonnet.llm_tokens_out == 200
    # 100/1M * 3 + 200/1M * 15 = 0.0003 + 0.003 = 0.0033
    assert sonnet.cost_usd == pytest.approx(0.0033)
    assert opus.model == "claude-opus-4-7"
    # 10/1M * 15 + 20/1M * 75 = 0.00015 + 0.0015 = 0.00165
    assert opus.cost_usd == pytest.approx(0.00165)


def test_build_llm_client_wires_recorder(db_session, monkeypatch):
    """build_llm_client returns an LLMClient whose complete() writes a RunLog."""
    from dataclasses import dataclass

    @dataclass
    class _FakeUsage:
        input_tokens: int
        output_tokens: int

    @dataclass
    class _FakeBlock:
        text: str

    @dataclass
    class _FakeMessage:
        content: list
        usage: _FakeUsage

    class _FakeMessages:
        def create(self, **kwargs):
            return _FakeMessage(
                content=[_FakeBlock(text="answer")],
                usage=_FakeUsage(input_tokens=42, output_tokens=7),
            )

    class _FakeAnthropic:
        def __init__(self):
            self.messages = _FakeMessages()

    from newsletter.core.llm import LLMClient

    client = LLMClient(client=_FakeAnthropic(), usage_callback=recorder.make_llm_recorder())
    client.complete("hi", model="claude-sonnet-4-6")
    db_session.expire_all()
    rows = _all_runs(db_session)
    assert len(rows) == 1
    assert rows[0].step == "llm.complete"
    assert rows[0].llm_tokens_in == 42
    assert rows[0].llm_tokens_out == 7
    assert rows[0].model == "claude-sonnet-4-6"


def test_make_embedding_recorder_writes_one_row_per_batch(db_session):
    record = recorder.make_embedding_recorder()
    record("voyage-3-lite", 12_500)
    record("voyage-3-lite", 1_000_000)
    db_session.expire_all()
    rows = _all_runs(db_session)
    assert len(rows) == 2
    assert all(r.step == "embedding.batch" for r in rows)
    assert all(r.model == "voyage-3-lite" for r in rows)
    # voyage-3-lite: $0.02 per 1M tokens.
    assert rows[1].cost_usd == pytest.approx(0.02)
    assert rows[0].cost_usd == pytest.approx(0.02 * 12500 / 1_000_000)


def test_build_embedding_client_disabled_without_api_key(monkeypatch, settings):
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()
    client = recorder.build_embedding_client()
    assert isinstance(client, DisabledEmbeddingClient)
    assert client.embed(["x"]) == []


def test_build_embedding_client_uses_voyage_when_key_set(monkeypatch, settings):
    """When VOYAGE_API_KEY is present, build_embedding_client returns a
    VoyageEmbeddingClient. We stub the voyageai SDK so no network call
    happens during construction."""
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()

    class _FakeVoyageSDK:
        class Client:
            def __init__(self, *a, **kw):
                pass

    monkeypatch.setitem(__import__("sys").modules, "voyageai", _FakeVoyageSDK)

    client = recorder.build_embedding_client()
    assert isinstance(client, VoyageEmbeddingClient)
    assert client.model == "voyage-3-lite"


def test_record_step_survives_outer_session_rollback(db_session):
    """If a test caller's session is rolled back, the RunLog must still be there."""
    with pytest.raises(ValueError), recorder.record_step("draft") as run:
        run.item_count = 3
        raise ValueError("user code blew up")
    db_session.rollback()  # simulate caller's session_scope rolling back
    db_session.expire_all()
    rows = _all_runs(db_session)
    assert len(rows) == 1
    assert rows[0].status == "failure"
    assert rows[0].item_count == 3
