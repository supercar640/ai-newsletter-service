"""Newsletter draft assembly (Iterations 6 + 7).

Pulls today's processed items through scoring/clustering/candidate
selection, runs both per-track section writers (expert + practical),
stitches a final markdown/HTML body, and persists a NewsletterIssue.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as date_cls
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.core.llm import LLMClient
from newsletter.core.logging import get_logger
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source
from newsletter.slices.departments import repository as dept_repo
from newsletter.slices.integration.candidates import Candidate
from newsletter.slices.integration.service import integrate
from newsletter.slices.newsletter.audiences import (
    DEFAULT_AUDIENCE,
    AudienceProfile,
    resolve_audience,
)
from newsletter.slices.newsletter.department_tips import (
    apply_department_tips,
    persist_department_tips,
    recent_tips_by_department,
)
from newsletter.slices.newsletter.expert import (
    ClusterBrief,
    ClusterMember,
    build_expert_section,
)
from newsletter.slices.newsletter.practical import build_practical_section

log = get_logger(__name__)

# Project-root templates/. Resolves to .../AI_newsletter_service/templates.
_TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "templates"

_MD = MarkdownIt("commonmark", {"html": False, "linkify": True})


@dataclass(slots=True, frozen=True)
class DraftReport:
    issue_id: int
    issue_date: date_cls
    audience: str
    expert_clusters_used: int
    practical_clusters_used: int
    candidate_count: int


def draft_issue(
    session: Session,
    *,
    today: date_cls,
    llm: LLMClient,
    scoring_llm: LLMClient | None = None,
    expert_count: int | None = None,
    practical_count: int | None = None,
    audience: str | None = None,
) -> DraftReport:
    """Build today's newsletter draft and persist it as a NewsletterIssue.

    Parameters
    ----------
    llm:
        Writer LLM used by the expert-section summarizer + writer.
    scoring_llm:
        Optional sonnet client passed to the integration's LLM-boost pass.
        ``None`` (the default) skips the boost — base trust * recency
        scores are still applied. Production wires both to the same client.
    expert_count / practical_count:
        Per-track candidate caps. When ``None`` (the default), the values
        come from the resolved :class:`AudienceProfile` — explicit kwargs
        override the profile for ad-hoc draft sizes.
    audience:
        Profile name (``general`` / ``executive`` / ``technical``). ``None``
        falls back to the default audience.

    Always inserts a *new* row — there is no upsert. Callers that want to
    replace an earlier same-day draft should delete it first.
    """
    profile = resolve_audience(audience)
    effective_expert = expert_count if expert_count is not None else profile.expert_count
    effective_practical = (
        practical_count if practical_count is not None else profile.practical_count
    )

    report = integrate(
        session,
        llm=scoring_llm,
        expert_count=effective_expert,
        practical_count=effective_practical,
    )

    expert_briefs = _resolve_briefs(session, report.expert_candidates)
    expert_section = build_expert_section(expert_briefs, date=today.isoformat(), llm=llm)

    practical_briefs = _resolve_briefs(session, report.practical_candidates)
    practical_section = build_practical_section(practical_briefs, date=today.isoformat(), llm=llm)

    # Phase 2: per-department tips — generate structured §2, accumulate, and
    # feed recent tips back so successive issues stay varied. No-op when no
    # departments are registered.
    departments = dept_repo.list_departments(session, only_enabled=True)
    if departments:
        recent = recent_tips_by_department(session, [d.name for d in departments])
        practical_section = apply_department_tips(
            practical_section, departments, recent, date=today.isoformat(), llm=llm
        )

    candidate_blob = {
        "expert": [{"id": c.id, "included": True} for c in report.expert_candidates],
        "practical": [{"id": c.id, "included": True} for c in report.practical_candidates],
    }

    title = _format_title(today, profile)
    markdown_body = _render_newsletter_md(
        title=title,
        expert_md=expert_section.markdown,
        practical_md=practical_section.markdown,
        template=profile.template,
    )
    html_body = _MD.render(markdown_body)

    issue = NewsletterIssue(
        issue_date=today,
        title=title,
        status="review_required",
        audience=profile.name,
        expert_section_md=expert_section.markdown,
        practical_section_md=practical_section.markdown,
        markdown_body=markdown_body,
        html_body=html_body,
        candidate_ids_json=json.dumps(candidate_blob, ensure_ascii=False),
    )
    session.add(issue)
    session.flush()
    session.refresh(issue)

    if practical_section.department_tips:
        persist_department_tips(session, issue.id, practical_section.department_tips)

    log.info(
        "newsletter.draft.created",
        issue_id=issue.id,
        issue_date=today.isoformat(),
        audience=profile.name,
        expert_clusters=len(report.expert_candidates),
        practical_clusters=len(report.practical_candidates),
    )
    return DraftReport(
        issue_id=issue.id,
        issue_date=today,
        audience=profile.name,
        expert_clusters_used=len(report.expert_candidates),
        practical_clusters_used=len(report.practical_candidates),
        candidate_count=len(report.expert_candidates) + len(report.practical_candidates),
    )


def _resolve_briefs(session: Session, candidates: list[Candidate]) -> list[ClusterBrief]:
    if not candidates:
        return []
    member_ids: list[int] = []
    for c in candidates:
        member_ids.extend(c.cluster_member_ids)
    by_id = _fetch_members(session, member_ids)
    briefs: list[ClusterBrief] = []
    for c in candidates:
        members = tuple(by_id[mid] for mid in c.cluster_member_ids if mid in by_id)
        if not members:
            continue
        briefs.append(ClusterBrief(cluster_id=c.cluster_id, score=c.score, members=members))
    return briefs


def _fetch_members(session: Session, ids: list[int]) -> dict[int, ClusterMember]:
    if not ids:
        return {}
    stmt = (
        select(ProcessedItem, RawItem, Source)
        .join(RawItem, RawItem.id == ProcessedItem.raw_item_id)
        .join(Source, Source.source_id == RawItem.source_id, isouter=True)
        .where(ProcessedItem.id.in_(ids))
    )
    out: dict[int, ClusterMember] = {}
    for proc, raw, source in session.execute(stmt).all():
        out[proc.id] = ClusterMember(
            id=proc.id,
            title=proc.normalized_title,
            url=raw.url if raw else "",
            summary=proc.summary,
            source_name=source.name if source else "(unknown)",
        )
    return out


_AUDIENCE_TITLE_SUFFIX = {
    "general": "최신 AI 동향과 업무 활용 인사이트",
    "executive": "임원 요약",
    "technical": "실무자용 상세",
}


def _format_title(today: date_cls, profile: AudienceProfile) -> str:
    suffix = _AUDIENCE_TITLE_SUFFIX.get(profile.name, _AUDIENCE_TITLE_SUFFIX[DEFAULT_AUDIENCE])
    return f"[AI 뉴스레터] {today.isoformat()} — {suffix}"


def _render_newsletter_md(
    *,
    title: str,
    expert_md: str,
    practical_md: str | None,
    template: str,
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=("md", "j2")),
        keep_trailing_newline=True,
    )
    tmpl = env.get_template(template)
    return tmpl.render(
        title=title,
        expert_section=expert_md,
        practical_section=practical_md,
    )


__all__ = ["DraftReport", "draft_issue"]
