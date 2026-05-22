"""Pydantic schemas for the Department registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DepartmentCreate(BaseModel):
    """Input for creating a new department."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = True


class DepartmentUpdate(BaseModel):
    """Partial update — every field optional."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None


class DepartmentRead(BaseModel):
    """Output shape exposed to callers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    enabled: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RelevantHeadline:
    title: str
    url: str
    score: float


@dataclass(frozen=True, slots=True)
class DepartmentDigestEntry:
    name: str
    headlines: list[RelevantHeadline]  # score desc, top_k


@dataclass(frozen=True, slots=True)
class DepartmentDigest:
    since: date
    until: date  # exclusive
    total_items: int  # items scanned in window
    mode: str  # "embedding" | "keyword"
    departments: list[DepartmentDigestEntry]  # enabled departments, by id
