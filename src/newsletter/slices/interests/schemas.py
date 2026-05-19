"""Pydantic schemas for the CompanyInterest registry."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InterestCreate(BaseModel):
    """Input for creating a new company interest."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    keywords: list[str] = Field(default_factory=list)
    weight: float = Field(default=1.0, ge=0.0, le=5.0)
    enabled: bool = True


class InterestUpdate(BaseModel):
    """Partial update — every field optional."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    keywords: list[str] | None = None
    weight: float | None = Field(default=None, ge=0.0, le=5.0)
    enabled: bool | None = None


class InterestRead(BaseModel):
    """Output shape exposed to callers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    keywords: list[str]
    weight: float
    enabled: bool
    embedding_model: str | None
    created_at: datetime
