"""Schemas for the competitor registry and the mention report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class CompetitorCreate(BaseModel):
    """Input for registering a new competitor."""

    name: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list)
    enabled: bool = True


class CompetitorUpdate(BaseModel):
    """Partial update — every field optional."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    aliases: list[str] | None = None
    enabled: bool | None = None


class CompetitorRead(BaseModel):
    """Output shape exposed to callers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    aliases: list[str]
    enabled: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Headline:
    """One mentioning article."""

    title: str
    url: str
    importance: float


@dataclass(frozen=True, slots=True)
class CompetitorMentions:
    """Per-competitor rollup in a report."""

    name: str
    count: int
    headlines: list[Headline]  # importance desc, truncated to top_k


@dataclass(frozen=True, slots=True)
class CompetitorReport:
    """Result of analyzing one look-back window."""

    since: date
    until: date  # exclusive upper bound
    total_items: int  # items scanned in window
    competitors: list[CompetitorMentions]  # count desc, then name asc
