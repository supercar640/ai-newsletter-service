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
