from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from newsletter.core.embeddings import EmbeddingClient
from newsletter.slices.competitors.report import render_markdown as render_competitors
from newsletter.slices.competitors.service import analyze_competitors
from newsletter.slices.dashboard.report import render_markdown as render_dashboard
from newsletter.slices.dashboard.service import build_dashboard
from newsletter.slices.departments.digest import build_department_digest
from newsletter.slices.departments.report import render_markdown as render_departments
from newsletter.slices.monthly.report import render_markdown as render_monthly
from newsletter.slices.monthly.service import build_monthly_report
from newsletter.slices.trends.report import render_markdown as render_trends
from newsletter.slices.trends.service import analyze_trends


@dataclass(frozen=True, slots=True)
class SitePage:
    slug: str
    title: str
    markdown: str


def build_site_pages(session: Session, *, embed_client: EmbeddingClient) -> list[SitePage]:
    """Build every report's (slug, title, markdown) using default windows."""
    return [
        SitePage("trends", "트렌드 리포트", render_trends(analyze_trends(session, period="week"))),
        SitePage(
            "competitors", "경쟁사 멘션 리포트", render_competitors(analyze_competitors(session))
        ),
        SitePage("monthly", "월간 AI 동향", render_monthly(build_monthly_report(session))),
        SitePage("dashboard", "성과 대시보드", render_dashboard(build_dashboard(session))),
        SitePage(
            "departments",
            "부서별 다이제스트",
            render_departments(build_department_digest(session, embed_client=embed_client)),
        ),
    ]


def build_index_markdown(pages: list[SitePage], *, generated_at: datetime) -> str:
    """Landing-page markdown linking each report by relative filename."""
    lines = [
        "# AI 인텔리전스 리포트",
        "",
        f"생성: {generated_at:%Y-%m-%d %H:%M}",
        "",
    ]
    lines.extend(f"- [{p.title}]({p.slug}.html)" for p in pages)
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["SitePage", "build_index_markdown", "build_site_pages"]
