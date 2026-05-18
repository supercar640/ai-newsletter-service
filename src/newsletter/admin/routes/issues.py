"""Issue list, review, and write-side action routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from markdown_it import MarkdownIt
from sqlalchemy.orm import Session

from newsletter.admin.data import get_issue_detail, list_issues
from newsletter.admin.deps import get_db
from newsletter.admin.services import (
    IssueStateError,
    approve_issue,
    reject_issue,
    toggle_candidate,
)
from newsletter.admin.templating import templates
from newsletter.models.newsletter_issue import NewsletterIssue

router = APIRouter(prefix="/issues")

_md = MarkdownIt("commonmark", {"html": False, "linkify": True})


@router.get("", response_class=HTMLResponse)
async def issue_list(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    rows = list_issues(db, limit=50)
    return templates.TemplateResponse(
        request=request,
        name="issues_list.html.j2",
        context={
            "title": "이슈 검수",
            "active_nav": "issues",
            "issues": rows,
        },
    )


@router.get("/{issue_id}", response_class=HTMLResponse)
async def issue_review(
    request: Request,
    issue_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    detail = get_issue_detail(db, issue_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    expert_html = _md.render(detail.issue.expert_section_md or "")
    practical_html = _md.render(detail.issue.practical_section_md or "")
    expert_included = sum(1 for c in detail.expert_candidates if c.included)
    practical_included = sum(1 for c in detail.practical_candidates if c.included)

    return templates.TemplateResponse(
        request=request,
        name="issue_review.html.j2",
        context={
            "title": f"검수 — {detail.issue.title}",
            "active_nav": "issues",
            "detail": detail,
            "expert_html": expert_html,
            "practical_html": practical_html,
            "expert_included": expert_included,
            "practical_included": practical_included,
        },
    )


def _load_issue_or_404(db: Session, issue_id: int) -> NewsletterIssue:
    issue = db.get(NewsletterIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return issue


def _redirect_to_review(issue_id: int) -> RedirectResponse:
    # 303 turns a POST into a GET on the next hop — standard PRG pattern.
    return RedirectResponse(f"/issues/{issue_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{issue_id}/toggle")
async def toggle_candidate_route(
    issue_id: int,
    track: str = Form(...),
    processed_item_id: int = Form(...),
    included: int = Form(...),  # 0 or 1
    db: Session = Depends(get_db),
) -> RedirectResponse:
    issue = _load_issue_or_404(db, issue_id)
    try:
        toggle_candidate(
            db,
            issue,
            track=track,
            processed_item_id=processed_item_id,
            included=bool(included),
        )
    except IssueStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _redirect_to_review(issue_id)


@router.post("/{issue_id}/approve")
async def approve_route(
    issue_id: int,
    approved_by: str = Form("master"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    issue = _load_issue_or_404(db, issue_id)
    try:
        approve_issue(db, issue, approved_by=approved_by)
    except IssueStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _redirect_to_review(issue_id)


@router.post("/{issue_id}/reject")
async def reject_route(
    issue_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    issue = _load_issue_or_404(db, issue_id)
    try:
        reject_issue(db, issue)
    except IssueStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _redirect_to_review(issue_id)
