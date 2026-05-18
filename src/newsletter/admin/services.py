"""Write-side issue operations.

State machine transitions are enforced here so routes can stay thin.

    drafted ⇄ review_required → approved → sent
                              ↘ rejected
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from newsletter.models.newsletter_issue import NewsletterIssue

VALID_TRACKS = ("expert", "practical")

_APPROVAL_SOURCE_STATES = ("drafted", "review_required")
_REJECT_BLOCKED_STATES = ("sent",)
_CANDIDATE_EDIT_BLOCKED_STATES = ("approved", "sent")


class IssueStateError(Exception):
    """Raised when an action is illegal for the current issue state."""


@dataclass(slots=True, frozen=True)
class ToggleResult:
    track: str
    processed_item_id: int
    included: bool


def toggle_candidate(
    session: Session,
    issue: NewsletterIssue,
    *,
    track: str,
    processed_item_id: int,
    included: bool,
    now: datetime | None = None,
) -> ToggleResult:
    if track not in VALID_TRACKS:
        raise IssueStateError(f"unknown track: {track}")
    if issue.status in _CANDIDATE_EDIT_BLOCKED_STATES:
        raise IssueStateError(f"이슈가 {issue.status} 상태라 후보를 수정할 수 없습니다.")

    blob = _load_blob(issue.candidate_ids_json)
    existing = blob.get(track) if isinstance(blob.get(track), list) else []
    new_arr: list[Any] = []
    found = False
    for entry in existing:
        pid = _entry_id(entry)
        if pid == processed_item_id:
            new_arr.append({"id": processed_item_id, "included": included})
            found = True
        else:
            new_arr.append(entry)
    if not found:
        new_arr.append({"id": processed_item_id, "included": included})

    blob[track] = new_arr
    issue.candidate_ids_json = json.dumps(blob)
    issue.updated_at = now or datetime.now(UTC)
    session.flush()
    return ToggleResult(track, processed_item_id, included)


def approve_issue(
    session: Session,
    issue: NewsletterIssue,
    *,
    approved_by: str,
    now: datetime | None = None,
) -> None:
    if issue.status not in _APPROVAL_SOURCE_STATES:
        raise IssueStateError(f"이슈가 {issue.status} 상태라 승인할 수 없습니다.")
    issue.status = "approved"
    issue.approved_by = approved_by
    issue.approved_at = now or datetime.now(UTC)
    session.flush()


def reject_issue(
    session: Session,
    issue: NewsletterIssue,
    *,
    now: datetime | None = None,
) -> None:
    if issue.status in _REJECT_BLOCKED_STATES:
        raise IssueStateError(f"이슈가 {issue.status} 상태라 거절할 수 없습니다.")
    issue.status = "rejected"
    issue.approved_by = None
    issue.approved_at = None
    issue.updated_at = now or datetime.now(UTC)
    session.flush()


def _load_blob(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _entry_id(entry: Any) -> int | None:
    if isinstance(entry, dict):
        pid = entry.get("id")
        return pid if isinstance(pid, int) else None
    if isinstance(entry, int):
        return entry
    return None
