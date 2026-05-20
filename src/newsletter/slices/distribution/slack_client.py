"""Minimal Slack Incoming Webhook client — POST one card per issue.

We hit the webhook directly with httpx (mirrors the Notion client): the whole
surface we use is a single POST of ``{"blocks": [...]}``. ``from_settings()``
returns ``None`` when no webhook is configured, which callers treat as "Slack
distribution is disabled".
"""

from __future__ import annotations

import httpx

from newsletter.core.config import get_settings
from newsletter.core.logging import get_logger

log = get_logger(__name__)

_TIMEOUT_SECONDS = 15.0


class SlackError(Exception):
    """Raised when the Slack webhook call fails (network, non-2xx)."""


class SlackClient:
    """Thin wrapper around a Slack Incoming Webhook URL."""

    def __init__(
        self,
        *,
        webhook_url: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not webhook_url:
            raise ValueError("Slack webhook_url must be non-empty")
        self._webhook_url = webhook_url
        self._http = http_client

    @classmethod
    def from_settings(cls) -> SlackClient | None:
        """Build a client from settings. ``None`` when not configured."""
        settings = get_settings()
        if not settings.slack_webhook_url:
            return None
        return cls(webhook_url=settings.slack_webhook_url)

    def post(self, blocks: list[dict]) -> None:
        """POST a Block Kit card to the webhook. Raises on failure."""
        body = {"blocks": blocks}
        try:
            client = self._http or httpx.Client(timeout=_TIMEOUT_SECONDS)
            close_after = self._http is None
            try:
                response = client.post(self._webhook_url, json=body)
            finally:
                if close_after:
                    client.close()
        except httpx.HTTPError as exc:
            raise SlackError(f"Slack request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text[:200]
            raise SlackError(f"Slack webhook returned {response.status_code}: {detail}")

        log.info("distribution.slack.posted", blocks=len(blocks))


__all__ = ["SlackClient", "SlackError"]
