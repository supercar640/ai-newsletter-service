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
from newsletter.slices.integration.candidates import Candidate
from newsletter.slices.integration.service import integrate
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
    expert_clusters_used: int
    practical_clusters_used: int
    candidate_count: int


def draft_issue(
    session: Session,
    *,
    today: date_cls,
    llm: LLMClient,
    scoring_llm: LLMClient | None = None,
    expert_count: int = 7,
    practical_count: int = 4,
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

    Always inserts a *new* row — there is no upsert. Callers that want to
    replace an earlier same-day draft should delete it first.
    """
    report = integrate(
        session,
        llm=scoring_llm,
        expert_count=expert_count,
        practical_count=practical_count,
    )

    expert_briefs = _resolve_briefs(session, report.expert_candidates)
    expert_section = build_expert_section(expert_briefs, date=today.isoformat(), llm=llm)

    practical_briefs = _resolve_briefs(session, report.practical_candidates)
    practical_section = build_practical_section(practical_briefs, date=today.isoformat(), llm=llm)

    candidate_blob = {
        "expert": [{"id": c.id, "included": True} for c in report.expert_candidates],
        "practical": [{"id": c.id, "included": True} for c in report.practical_candidates],
    }

    title = _format_title(today)
    markdown_body = _render_newsletter_md(
        title=title,
        expert_md=expert_section.markdown,
        practical_md=practical_section.markdown,
    )
    html_body = _MD.render(markdown_body)

    issue = NewsletterIssue(
        issue_date=today,
        title=title,
        status="review_required",
        expert_section_md=expert_section.markdown,
        practical_section_md=practical_section.markdown,
        markdown_body=markdown_body,
        html_body=html_body,
        candidate_ids_json=json.dumps(candidate_blob, ensure_ascii=False),
    )
    session.add(issue)
    session.flush()
    session.refresh(issue)

    log.info(
        "newsletter.draft.created",
        issue_id=issue.id,
        issue_date=today.isoformat(),
        expert_clusters=len(report.expert_candidates),
        practical_clusters=len(report.practical_candidates),
    )
    return DraftReport(
        issue_id=issue.id,
        issue_date=today,
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


def _format_title(today: date_cls) -> str:
    return f"[AI 뉴스레터] {today.isoformat()} — 최신 AI 동향과 업무 활용 인사이트"


def _render_newsletter_md(
    *,
    title: str,
    expert_md: str,
    practical_md: str | None,
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=("md", "j2")),
        keep_trailing_newline=True,
    )
    tmpl = env.get_template("newsletter.md.j2")
    return tmpl.render(
        title=title,
        expert_section=expert_md,
        practical_section=practical_md,
    )


__all__ = ["DraftReport", "draft_issue"]
