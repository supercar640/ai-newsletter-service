"""draft_issue: audience-aware count + template routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import date as date_cls

from newsletter.core.llm import LLMResponse
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source
from newsletter.slices.newsletter.assembler import draft_issue

TODAY = date_cls(2026, 5, 19)


@dataclass
class _StubLLM:
    json_payload: dict = field(
        default_factory=lambda: {
            "title": "스텁 제목",
            "summary": "스텁 요약.",
            "why_it_matters": "스텁 중요도.",
            "company_perspective": "스텁 관점.",
            "scenario": "x",
            "method": "x",
            "prompt_example": "x",
            "caveats": "x",
            "sources": [],
        }
    )
    writer_text: str = "stubbed output"

    def complete_json(self, body, *, tier, max_tokens=1024):
        return (self.json_payload, None)

    def complete(self, body, *, tier, max_tokens=4096, system=None, temperature=0.2):
        return LLMResponse(text=self.writer_text, model=tier, input_tokens=0, output_tokens=0)


def _seed_pool(db_session, count: int):
    src = Source(
        source_id="src",
        name="src",
        type="RSS",
        content_track="expert_news",
        endpoint="https://example.com",
        priority="medium",
        trust_level="media",
        fetch_interval="daily",
    )
    db_session.add(src)
    db_session.flush()
    for i in range(count):
        raw = RawItem(
            source_id="src",
            title=f"topic_{i}",
            url=f"https://example.com/{i}",
            collected_at=datetime.now(UTC),
        )
        db_session.add(raw)
        db_session.flush()
        # single-token titles → each its own cluster
        db_session.add(
            ProcessedItem(
                raw_item_id=raw.id,
                normalized_title=f"topic_{i}",
                canonical_url=raw.url,
                content_track="expert_news" if i % 2 == 0 else "practical_insight",
                summary=f"summary {i}",
            )
        )
    db_session.commit()


def test_default_audience_is_general(db_session):
    report = draft_issue(db_session, today=TODAY, llm=_StubLLM())
    db_session.commit()
    issue = db_session.get(NewsletterIssue, report.issue_id)
    assert report.audience == "general"
    assert issue.audience == "general"
    assert "최신 AI 동향" in issue.title


def test_executive_uses_smaller_caps_and_executive_template(db_session):
    _seed_pool(db_session, 30)
    report = draft_issue(
        db_session,
        today=TODAY,
        llm=_StubLLM(),
        audience="executive",
    )
    db_session.commit()
    issue = db_session.get(NewsletterIssue, report.issue_id)
    assert report.audience == "executive"
    assert issue.audience == "executive"
    # executive caps are 3 + 2 from audiences.py.
    assert report.expert_clusters_used <= 3
    assert report.practical_clusters_used <= 2
    # The executive template starts with the leadership summary header.
    assert "임원 요약본" in issue.markdown_body
    assert "임원 요약" in issue.title


def test_technical_uses_larger_caps_and_technical_template(db_session):
    _seed_pool(db_session, 50)
    report = draft_issue(
        db_session,
        today=TODAY,
        llm=_StubLLM(),
        audience="technical",
    )
    db_session.commit()
    issue = db_session.get(NewsletterIssue, report.issue_id)
    assert report.audience == "technical"
    assert issue.audience == "technical"
    assert report.expert_clusters_used <= 10
    assert report.practical_clusters_used <= 6
    assert "실무자용 상세본" in issue.markdown_body


def test_explicit_count_overrides_audience_defaults(db_session):
    _seed_pool(db_session, 30)
    report = draft_issue(
        db_session,
        today=TODAY,
        llm=_StubLLM(),
        audience="executive",
        expert_count=5,
        practical_count=4,
    )
    db_session.commit()
    # CLI/test overrides win even when an audience is set.
    assert report.expert_clusters_used <= 5
    assert report.practical_clusters_used <= 4


def test_unknown_audience_raises(db_session):
    import pytest

    with pytest.raises(ValueError, match="audience"):
        draft_issue(db_session, today=TODAY, llm=_StubLLM(), audience="intern")


def test_general_audience_uses_legacy_template(db_session):
    report = draft_issue(db_session, today=TODAY, llm=_StubLLM(), audience="general")
    db_session.commit()
    issue = db_session.get(NewsletterIssue, report.issue_id)
    # The default template starts with the two-section intro.
    assert "AI 전문가가 볼 만한" in issue.markdown_body
