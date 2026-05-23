"""Minimal Notion REST client — just enough to create one page per issue.

We hit the Notion API directly with httpx rather than depending on
``notion-client``. Two reasons:

* The whole surface we use is a single POST to ``/v1/pages``.
* We can mock the calls with ``respx`` like everything else in the suite.

If the archive grows (search, update, comments), swapping in the official
SDK is a one-file change.
"""

from __future__ import annotations

from typing import Any

import httpx

from newsletter.core.config import get_settings
from newsletter.core.logging import get_logger

log = get_logger(__name__)

_NOTION_API_BASE = "https://api.notion.com/v1"
_TIMEOUT_SECONDS = 15.0


class NotionError(Exception):
    """Raised when the Notion API call fails (network, auth, validation)."""


class NotionClient:
    """Thin wrapper around the Notion REST API."""

    def __init__(
        self,
        *,
        token: str,
        database_id: str,
        api_version: str = "2022-06-28",
        http_client: httpx.Client | None = None,
    ) -> None:
        if not token:
            raise ValueError("Notion token must be non-empty")
        if not database_id:
            raise ValueError("Notion database_id must be non-empty")
        self._token = token
        self.database_id = database_id
        self._api_version = api_version
        self._http = http_client

    @classmethod
    def from_settings(cls) -> NotionClient | None:
        """Build a client from settings. Returns ``None`` when not configured.

        Callers (the archive service / CLI) treat ``None`` as "Notion archive
        is disabled" — equivalent to the embedding client pattern.
        """
        settings = get_settings()
        if not settings.notion_token or not settings.notion_database_id:
            return None
        return cls(
            token=settings.notion_token,
            database_id=settings.notion_database_id,
            api_version=settings.notion_api_version,
        )

    def create_page(
        self,
        *,
        title: str,
        properties: dict[str, Any],
        children: list[dict[str, Any]],
    ) -> str:
        """Create a new database page and return its Notion page id.

        ``properties`` is merged with the auto-generated ``Name`` title
        field; pass any additional database columns the operator has
        configured (date, select, etc.).
        """
        body: dict[str, Any] = {
            "parent": {"database_id": self.database_id},
            "properties": {
                **properties,
                "Name": {"title": [{"type": "text", "text": {"content": title}}]},
            },
            "children": children,
        }
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": self._api_version,
            "Content-Type": "application/json",
        }
        url = f"{_NOTION_API_BASE}/pages"
        try:
            client = self._http or httpx.Client(timeout=_TIMEOUT_SECONDS)
            close_after = self._http is None
            try:
                response = client.post(url, json=body, headers=headers)
            finally:
                if close_after:
                    client.close()
        except httpx.HTTPError as exc:
            raise NotionError(f"Notion request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = _safe_error_message(response)
            raise NotionError(f"Notion API returned {response.status_code}: {detail}")

        payload = response.json()
        page_id = str(payload.get("id") or "")
        if not page_id:
            raise NotionError(f"Notion response missing page id: {payload!r}")
        return page_id


def _safe_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        return response.text[:200]
    if isinstance(body, dict):
        msg = body.get("message") or body.get("code") or ""
        return str(msg)[:200]
    return str(body)[:200]


__all__ = ["NotionClient", "NotionError"]
