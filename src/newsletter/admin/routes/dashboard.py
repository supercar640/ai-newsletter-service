"""Dashboard route — pipeline stats + recent issues."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.admin.data import get_dashboard_stats, list_recent_issues
from newsletter.admin.deps import get_db
from newsletter.admin.templating import templates
from newsletter.models.newsletter_issue import NewsletterIssue

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    today = datetime.now(UTC).date()
    stats = get_dashboard_stats(db, today)
    recent = list_recent_issues(db, limit=10)
    today_issue = db.scalar(
        select(NewsletterIssue)
        .where(NewsletterIssue.issue_date == today)
        .order_by(NewsletterIssue.id.desc())
        .limit(1)
    )
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html.j2",
        context={
            "title": "Dashboard",
            "active_nav": "dashboard",
            "stats": stats,
            "recent_issues": recent,
            "today": today,
            "today_issue_id": today_issue.id if today_issue else None,
        },
    )
