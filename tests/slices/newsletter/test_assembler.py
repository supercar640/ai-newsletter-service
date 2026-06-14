"""Assembler tests (Iteration 7).

Integration is invoked end-to-end with an in-memory DB. The expert
section LLM is stubbed — no scoring-boost LLM is passed, so the
integration stays deterministic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import date as date_cls

from newsletter.core.llm import LLMResponse
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source
from newsletter.slices.newsletter.assembler import draft_issue

TODAY = date_cls(2026, 5, 18)


@dataclass
class _StubLLM:
    """Stub that mimics LLMClient: complete_json + complete."""

    json_payload: dict = field(
        default_factory=lambda: {
            # expert summarizer fields
            "title": "스텁 제목",
            "summary": "스텁 요약입니다.",
            "why_it_matters": "스텁 중요도.",
            "company_perspective": "스텁 회사 관점.",
            # practical summarizer fields
            "scenario": "스텁 시나리오.",
            "method": "스텁 사용 방법.",
            "prompt_example": "스텁 예시 프롬프트.",
            "caveats": "스텁 주의사항.",
            "sources": [],
        }
    )
    writer_text: str = "stubbed opus output."
    json_calls: list[str] = field(default_factory=list)
    text_calls: list[str] = field(default_factory=list)

    def complete_json(self, body, *, tier, max_tokens=1024):
        self.json_calls.append(body)
        return (self.json_payload, None)

    def complete(self, body, *, tier, max_tokens=4096, system=None, temperature=0.2):
        self.text_calls.append(body)
        return LLMResponse(text=self.writer_text, model=tier, input_tokens=0, output_tokens=0)


def _seed_source(db_session, source_id: str = "src1") -> Source:
    src = Source(
        source_id=source_id,
        name="Test Source",
        type="RSS",
        content_track="expert_news",
        endpoint="http://example.com/feed",
        priority="medium",
        trust_level="media",
        fetch_interval="daily",
    )
    db_session.add(src)
    db_session.flush()
    return src


def _seed_item(
    db_session,
    src: Source,
    *,
    title: str,
    track: str = "expert_news",
    url: str | None = None,
) -> ProcessedItem:
    item_url = url or f"http://example.com/{title.replace(' ', '-')}"
    raw = RawItem(
        source_id=src.source_id,
        title=title,
        url=item_url,
        collected_at=datetime.now(UTC),
    )
    db_session.add(raw)
    db_session.flush()
    proc = ProcessedItem(
        raw_item_id=raw.id,
        normalized_title=title,
        canonical_url=item_url,
        content_track=track,
        summary=f"summary of {title}",
    )
    db_session.add(proc)
    db_session.flush()
    return proc


def test_draft_issue_with_empty_db_creates_placeholder_issue(db_session):
    llm = _StubLLM()
    report = draft_issue(db_session, today=TODAY, llm=llm)
    db_session.commit()

    assert report.issue_id is not None
    issue = db_session.get(NewsletterIssue, report.issue_id)
    assert issue is not None
    assert issue.status == "review_required"
    assert issue.issue_date == TODAY
    assert issue.title == "[AI 뉴스레터] 2026-05-18 — 최신 AI 동향과 업무 활용 인사이트"
    # No items → both sections render their _empty_section placeholders.
    assert "A. AI 전문가용 최신 AI 뉴스" in issue.markdown_body
    assert "B. 일반 임직원용 AI 활용 인사이트" in issue.markdown_body
    assert "이번 주 해당 내용 없음" in issue.markdown_body
    blob = json.loads(issue.candidate_ids_json)
    assert blob == {"expert": [], "practical": []}
    # Writer LLMs not invoked when there are no clusters in either track.
    assert llm.json_calls == []
    assert llm.text_calls == []


def test_draft_issue_with_items_invokes_writer(db_session):
    src = _seed_source(db_session)
    # Distinct titles so the Jaccard clusterer keeps each item in its own cluster.
    expert_titles = ("Llama 4 출시", "Anthropic 새 모델", "Google Gemini 업데이트")
    practical_titles = ("회의록 자동 정리", "보고서 초안 생성")
    expert_items = [
        _seed_item(db_session, src, title=t, track="expert_news") for t in expert_titles
    ]
    practical_items = [
        _seed_item(db_session, src, title=t, track="practical_insight") for t in practical_titles
    ]
    db_session.commit()

    llm = _StubLLM()
    report = draft_issue(db_session, today=TODAY, llm=llm)
    db_session.commit()

    assert report.expert_clusters_used == 3
    assert report.practical_clusters_used == 2

    issue = db_session.get(NewsletterIssue, report.issue_id)
    assert "stubbed opus output" in issue.expert_section_md
    assert "stubbed opus output" in issue.practical_section_md
    assert "stubbed opus output" in issue.markdown_body

    blob = json.loads(issue.candidate_ids_json)
    assert {e["id"] for e in blob["expert"]} == {it.id for it in expert_items}
    assert {e["id"] for e in blob["practical"]} == {it.id for it in practical_items}
    assert all(e["included"] for e in blob["expert"])
    # Summarizer called once per cluster across both tracks (3 + 2 = 5);
    # both section writers invoked once each.
    assert len(llm.json_calls) == 5
    assert len(llm.text_calls) == 2


def test_draft_issue_html_body_is_rendered(db_session):
    llm = _StubLLM()
    report = draft_issue(db_session, today=TODAY, llm=llm)
    db_session.commit()
    issue = db_session.get(NewsletterIssue, report.issue_id)
    # Markdown → HTML conversion happened, body wrapped in <h1>/<p>
    assert "<h1>" in issue.html_body
    assert "AI 뉴스레터" in issue.html_body


def test_draft_issue_respects_count_limits(db_session):
    src = _seed_source(db_session)
    # Single-token titles never share any token, so each becomes its own cluster.
    for i in range(12):
        _seed_item(db_session, src, title=f"expert_topic_{i}", track="expert_news")
    for i in range(10):
        _seed_item(db_session, src, title=f"practical_topic_{i}", track="practical_insight")
    db_session.commit()

    llm = _StubLLM()
    report = draft_issue(
        db_session,
        today=TODAY,
        llm=llm,
        expert_count=5,
        practical_count=3,
    )
    db_session.commit()
    assert report.expert_clusters_used == 5
    assert report.practical_clusters_used == 3
