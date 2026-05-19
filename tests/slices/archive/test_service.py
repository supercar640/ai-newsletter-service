"""archive.service — archive_issue + backfill."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.archive import service as archive_service
from newsletter.slices.archive.service import (
    AlreadyArchivedError,
    ArchiveDisabledError,
    archive_issue,
    backfill_archive,
)


class _FakeNotion:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._next_id = 100

    def create_page(self, *, title, properties, children):
        self.calls.append({"title": title, "properties": properties, "children": children})
        page_id = f"page-{self._next_id}"
        self._next_id += 1
        return page_id

    @property
    def database_id(self) -> str:
        return "db-1"


def _make_issue(
    db_session,
    *,
    status: str = "sent",
    audience: str | None = "general",
    notion_page_id: str | None = None,
    title: str = "Issue Title",
    markdown_body: str = "# Heading\n\nParagraph body.",
) -> NewsletterIssue:
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 19),
        title=title,
        status=status,
        audience=audience,
        markdown_body=markdown_body,
        html_body="<h1>x</h1>",
        notion_page_id=notion_page_id,
    )
    if status == "sent":
        issue.sent_at = datetime(2026, 5, 19, 9, 0, tzinfo=UTC)
    db_session.add(issue)
    db_session.commit()
    db_session.refresh(issue)
    return issue


def test_archive_issue_stores_page_id_and_timestamp(db_session):
    issue = _make_issue(db_session)
    client = _FakeNotion()
    report = archive_issue(db_session, issue, client=client)
    db_session.commit()
    db_session.refresh(issue)
    assert report.page_id == "page-100"
    assert issue.notion_page_id == "page-100"
    assert issue.archived_at is not None
    assert len(client.calls) == 1
    sent = client.calls[0]
    assert sent["title"] == "Issue Title"
    # children include a heading + a paragraph from the markdown body.
    types = [c["type"] for c in sent["children"]]
    assert "heading_1" in types
    assert "paragraph" in types


def test_archive_issue_passes_audience_and_date_as_properties(db_session):
    issue = _make_issue(db_session, audience="executive")
    client = _FakeNotion()
    archive_issue(db_session, issue, client=client)
    props = client.calls[0]["properties"]
    assert props["Audience"] == {"select": {"name": "executive"}}
    assert props["Date"]["date"]["start"] == "2026-05-19"
    assert props["Status"] == {"select": {"name": "sent"}}


def test_archive_issue_skips_already_archived(db_session):
    issue = _make_issue(db_session, notion_page_id="existing-page")
    client = _FakeNotion()
    with pytest.raises(AlreadyArchivedError):
        archive_issue(db_session, issue, client=client)
    assert client.calls == []


def test_archive_issue_allows_force_reupload(db_session):
    issue = _make_issue(db_session, notion_page_id="existing-page")
    client = _FakeNotion()
    archive_issue(db_session, issue, client=client, force=True)
    db_session.commit()
    db_session.refresh(issue)
    # force replaces the page id with the new one.
    assert issue.notion_page_id == "page-100"


def test_archive_issue_with_no_client_raises_disabled(db_session):
    issue = _make_issue(db_session)
    with pytest.raises(ArchiveDisabledError):
        archive_issue(db_session, issue, client=None)


def test_backfill_archives_every_sent_issue_without_page_id(db_session):
    a = _make_issue(db_session, title="a")
    b = _make_issue(db_session, title="b")
    # Already-archived row — must be left alone.
    c = _make_issue(db_session, title="c", notion_page_id="old-page")
    # Not-yet-sent — must not be touched.
    _make_issue(db_session, title="d", status="approved")

    client = _FakeNotion()
    report = backfill_archive(db_session, client=client)
    db_session.commit()
    db_session.refresh(a)
    db_session.refresh(b)
    db_session.refresh(c)
    assert {a.notion_page_id, b.notion_page_id} == {"page-100", "page-101"}
    assert c.notion_page_id == "old-page"  # untouched
    assert report.archived_count == 2
    assert report.skipped_count == 1  # c (already archived)


def test_backfill_continues_when_a_single_archive_fails(db_session, monkeypatch):
    _make_issue(db_session, title="a")
    _make_issue(db_session, title="b")

    class _FlakyNotion(_FakeNotion):
        def create_page(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise archive_service.NotionError("transient")
            return "page-ok"

    client = _FlakyNotion()
    report = backfill_archive(db_session, client=client)
    assert report.archived_count == 1
    assert len(report.errors) == 1
