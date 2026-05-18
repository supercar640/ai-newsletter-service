"""Send-confirm screen + send-action route.

The actual SMTP send lives in the distribution slice (Iteration 9). This
route enforces the spec gate — only ``approved`` issues are eligible —
and supports a dry-run path so the UI flow is testable before SMTP lands.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from newsletter.admin.deps import get_db
from newsletter.admin.templating import templates
from newsletter.core.config import get_settings
from newsletter.models.newsletter_issue import NewsletterIssue

router = APIRouter(prefix="/issues")


def _load_issue_or_404(db: Session, issue_id: int) -> NewsletterIssue:
    issue = db.get(NewsletterIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return issue


@router.get("/{issue_id}/send", response_class=HTMLResponse)
async def send_confirm(
    request: Request,
    issue_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    issue = _load_issue_or_404(db, issue_id)
    settings = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="send_confirm.html.j2",
        context={
            "title": f"발송 — {issue.title}",
            "active_nav": "issues",
            "issue": issue,
            "recipients": settings.recipient_list,
            "smtp_from": settings.smtp_from,
            "smtp_host": settings.smtp_host,
            "is_approved": issue.status == "approved",
        },
    )


@router.post("/{issue_id}/send")
async def send_action(
    issue_id: int,
    dry_run: int = Form(1),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    issue = _load_issue_or_404(db, issue_id)
    if issue.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"이슈가 {issue.status} 상태라 발송할 수 없습니다. "
                "approved 상태에서만 발송 가능합니다."
            ),
        )
    if dry_run:
        return RedirectResponse(
            f"/issues/{issue_id}?sent=dryrun",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    # Real SMTP send arrives with the distribution slice (Iteration 9).
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="실제 SMTP 발송은 아직 구현되지 않았습니다.",
    )
