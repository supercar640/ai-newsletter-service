"""distribution.card — issue → Slack Block Kit summary card (pure function)."""

from __future__ import annotations

from datetime import date

from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.distribution.card import build_card

_BODY_WITH_HEADLINES = """\
## A. AI 전문가용 최신 AI 뉴스

#### 뉴스 1. OpenAI가 새 모델을 공개했다
- 요약: ...

#### 뉴스 2. 구글이 제미나이를 업데이트했다
- 요약: ...

## B. 일반 임직원용 AI 활용 인사이트

#### 활용 1. 회의록 자동 요약
- 요약: ...
"""


def _make_issue(
    *,
    title: str = "2026-05-20 AI 인텔리전스",
    audience: str | None = "general",
    markdown_body: str = _BODY_WITH_HEADLINES,
    notion_page_id: str | None = None,
) -> NewsletterIssue:
    return NewsletterIssue(
        issue_date=date(2026, 5, 20),
        title=title,
        status="approved",
        audience=audience,
        markdown_body=markdown_body,
        notion_page_id=notion_page_id,
    )


def _text_blob(blocks: list[dict]) -> str:
    """All text in the card flattened, for substring assertions."""
    import json

    return json.dumps(blocks, ensure_ascii=False)


def test_card_header_contains_title():
    blocks = build_card(_make_issue())
    header = blocks[0]
    assert header["type"] == "header"
    assert "2026-05-20 AI 인텔리전스" in header["text"]["text"]


def test_card_context_contains_date_and_audience():
    blocks = build_card(_make_issue(audience="executive"))
    blob = _text_blob(blocks)
    assert "2026-05-20" in blob
    assert "executive" in blob


def test_card_null_audience_renders_as_general():
    blocks = build_card(_make_issue(audience=None))
    assert "general" in _text_blob(blocks)


def test_card_highlights_come_from_h4_headlines():
    blocks = build_card(_make_issue())
    blob = _text_blob(blocks)
    assert "OpenAI가 새 모델을 공개했다" in blob
    assert "회의록 자동 요약" in blob
    # The '#### ' prefix must be stripped.
    assert "####" not in blob


def test_card_caps_highlights_at_max():
    blocks = build_card(_make_issue(), max_highlights=2)
    blob = _text_blob(blocks)
    assert "OpenAI가 새 모델을 공개했다" in blob
    assert "구글이 제미나이를 업데이트했다" in blob
    assert "회의록 자동 요약" not in blob  # 3rd headline dropped


def test_card_falls_back_to_text_lines_without_h4():
    body = "## A. 섹션\n\n첫 번째 의미 있는 줄.\n두 번째 줄.\n"
    blocks = build_card(_make_issue(markdown_body=body))
    blob = _text_blob(blocks)
    assert "첫 번째 의미 있는 줄" in blob


def test_card_has_notion_button_when_archived():
    issue = _make_issue(notion_page_id="abc-123-def")
    blocks = build_card(issue)
    buttons = [
        el
        for b in blocks
        if b["type"] == "actions"
        for el in b["elements"]
        if el["type"] == "button"
    ]
    assert len(buttons) == 1
    # dashes stripped to form the notion.so URL.
    assert buttons[0]["url"] == "https://www.notion.so/abc123def"


def test_card_omits_button_without_notion_page():
    blocks = build_card(_make_issue(notion_page_id=None))
    assert all(b["type"] != "actions" for b in blocks)
