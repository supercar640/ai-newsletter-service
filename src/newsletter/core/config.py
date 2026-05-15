"""Application settings loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Values come from environment variables and `.env`. Field names map
    case-insensitively to env var names (e.g. ``ANTHROPIC_API_KEY``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = Field(default="", description="Claude API key")

    # Naver Search Open API
    naver_client_id: str = Field(default="")
    naver_client_secret: str = Field(default="")

    # YouTube Data API v3
    youtube_api_key: str = Field(default="")
    youtube_fetch_metadata: bool = Field(default=True)

    # YouTube search collector (YOUTUBE_SEARCH source type)
    youtube_search_top_n: int = Field(default=3, ge=1, le=50)
    youtube_search_region: str = Field(default="KR")
    # Set to 0 to skip downloading + transcribing audio (faster, no transcript).
    youtube_stt_enabled: bool = Field(default=True)
    # faster-whisper: model size + compute type + language hint
    whisper_model: str = Field(default="small")
    whisper_compute_type: str = Field(default="int8")
    whisper_device: str = Field(default="cpu")
    whisper_language: str = Field(default="")  # "" = auto-detect

    # Where on disk to write per-run artifacts (audio, scraped HTML, transcripts).
    data_dir: str = Field(default="data")

    # SMTP
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="")
    newsletter_recipients: str = Field(
        default="",
        description="Comma-separated list of recipient emails.",
    )

    # DB
    db_url: str = Field(default="sqlite:///data/newsletter.db")

    # Runtime
    log_format: Literal["json", "console"] = Field(default="console")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    env: Literal["development", "test", "production"] = Field(default="development")

    @property
    def recipient_list(self) -> list[str]:
        return [r.strip() for r in self.newsletter_recipients.split(",") if r.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
