"""Build a Slack Block Kit summary card from a NewsletterIssue.

Pure function — no DB, no network. Highlights are extracted deterministically
from the issue's markdown body (the per-item ``#### `` headlines), so no extra
LLM call is needed. The full newsletter goes out by email; this is the
lightweight card.
"""

from __future__ import annotations

from newsletter.models.newsletter_issue import NewsletterIssue

_MAX_HIGHLIGHTS = 5


def build_card(issue: NewsletterIssue, *, max_highlights: int = _MAX_HIGHLIGHTS) -> list[dict]:
    """Return Slack Block Kit ``blocks`` for ``issue``."""
    audience = issue.audience or "general"
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📰 {issue.title}", "emoji": True},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{issue.issue_date.isoformat()} · {audience}",
                }
            ],
        },
    ]

    highlights = _extract_highlights(issue.markdown_body or "", max_highlights)
    if highlights:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(f"• {h}" for h in highlights),
                },
            }
        )

    if issue.notion_page_id:
        page_id = issue.notion_page_id.replace("-", "")
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "아카이브에서 보기"},
                        "url": f"https://www.notion.so/{page_id}",
                    }
                ],
            }
        )

    return blocks


def _extract_highlights(markdown: str, limit: int) -> list[str]:
    """Pull up to ``limit`` highlight lines from the markdown body.

    Primary source: per-item ``#### `` headlines. If there are none (e.g. a
    fallback section writer produced a different shape), fall back to the first
    non-heading, non-empty text lines.
    """
    headlines = [line[5:].strip() for line in markdown.splitlines() if line.startswith("#### ")]
    if headlines:
        return headlines[:limit]

    fallback = [
        line.strip()
        for line in markdown.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return fallback[:limit]


__all__ = ["build_card"]
