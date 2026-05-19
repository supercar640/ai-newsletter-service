"""Audience profiles for newsletter template diversification (Phase 2).

Each profile decides how many candidates to keep per track and which
Jinja2 template the assembler will render. Same upstream pipeline (collect
→ process → integrate → write sections) — only the *presentation* differs
per audience, so we don't fragment the candidate selection.

Adding a new audience: append an :class:`AudienceProfile` to
:data:`AUDIENCES` and ship a matching template in ``templates/``. No code
changes elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(slots=True, frozen=True)
class AudienceProfile:
    """How much content + which template to render for one reader group."""

    name: str
    expert_count: int
    practical_count: int
    template: str
    description: str


AUDIENCES: Final[dict[str, AudienceProfile]] = {
    "general": AudienceProfile(
        name="general",
        expert_count=7,
        practical_count=4,
        template="newsletter.md.j2",
        description="기본 — 전사 임직원 대상, 전체 섹션을 모두 포함합니다.",
    ),
    "executive": AudienceProfile(
        name="executive",
        expert_count=3,
        practical_count=2,
        template="newsletter-executive.md.j2",
        description="임원용 — 핵심 헤드라인 + 영향도 위주의 압축 포맷.",
    ),
    "technical": AudienceProfile(
        name="technical",
        expert_count=10,
        practical_count=6,
        template="newsletter-technical.md.j2",
        description="실무자용 — 더 많은 항목 + 기술 세부 및 원문 링크 강조.",
    ),
}

DEFAULT_AUDIENCE: Final[str] = "general"


def resolve_audience(name: str | None) -> AudienceProfile:
    """Look up a profile by name. ``None`` returns the default."""
    if name is None:
        return AUDIENCES[DEFAULT_AUDIENCE]
    if name not in AUDIENCES:
        raise ValueError(
            f"unknown audience {name!r}. choose one of: {', '.join(AUDIENCES)}"
        )
    return AUDIENCES[name]


__all__ = [
    "AUDIENCES",
    "DEFAULT_AUDIENCE",
    "AudienceProfile",
    "resolve_audience",
]
