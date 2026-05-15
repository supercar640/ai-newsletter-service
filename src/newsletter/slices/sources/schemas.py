"""Pydantic schemas for the Source Registry.

These are the public contract for repository / CLI input/output. They
validate enum-like fields before they hit the DB CHECK constraints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal["NAVER_API", "RSS", "YOUTUBE_RSS", "YOUTUBE_SEARCH", "API", "MANUAL"]
ContentTrack = Literal["expert_news", "practical_insight", "both"]
Priority = Literal["high", "medium", "low"]
TrustLevel = Literal["official", "media", "community"]
FetchInterval = Literal["hourly", "daily", "weekly"]
AudienceLevel = Literal["beginner", "intermediate", "expert"]


class SourceCreate(BaseModel):
    """Input for creating a new source. Mirrors the table, minus timestamps."""

    source_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=200)
    type: SourceType
    content_track: ContentTrack
    endpoint: str = Field(min_length=1, max_length=1024)
    query: str | None = Field(default=None, max_length=500)
    language: str | None = Field(default=None, max_length=8)
    region: str | None = Field(default=None, max_length=16)
    category: str | None = Field(default=None, max_length=64)
    audience_level: AudienceLevel | None = None
    priority: Priority = "medium"
    trust_level: TrustLevel = "media"
    enabled: bool = True
    fetch_interval: FetchInterval = "daily"
    auth_required: bool = False
    rate_limit_note: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=64)


class SourceUpdate(BaseModel):
    """Partial update — every field optional."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: SourceType | None = None
    content_track: ContentTrack | None = None
    endpoint: str | None = Field(default=None, min_length=1, max_length=1024)
    query: str | None = Field(default=None, max_length=500)
    language: str | None = Field(default=None, max_length=8)
    region: str | None = Field(default=None, max_length=16)
    category: str | None = Field(default=None, max_length=64)
    audience_level: AudienceLevel | None = None
    priority: Priority | None = None
    trust_level: TrustLevel | None = None
    enabled: bool | None = None
    fetch_interval: FetchInterval | None = None
    auth_required: bool | None = None
    rate_limit_note: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=64)


class SourceRead(BaseModel):
    """Output shape with all persisted fields."""

    model_config = ConfigDict(from_attributes=True)

    source_id: str
    name: str
    type: SourceType
    content_track: ContentTrack
    endpoint: str
    query: str | None
    language: str | None
    region: str | None
    category: str | None
    audience_level: AudienceLevel | None
    priority: Priority
    trust_level: TrustLevel
    enabled: bool
    fetch_interval: FetchInterval
    auth_required: bool
    rate_limit_note: str | None
    owner: str | None
    created_at: datetime
    updated_at: datetime
