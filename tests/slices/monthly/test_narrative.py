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

    def complete(self, body: str, *, tier: str, max_tokens: int) -> LLMResponse:
        self.last_body = body
        if self.error:
            raise LLMError("boom")
        return LLMResponse(text=self.text, model=tier, input_tokens=1, output_tokens=1)


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
    assert "GPT-5 launch" in fake.last_body
    assert "secret body text" not in fake.last_body  # raw_summary must not leak to the LLM
