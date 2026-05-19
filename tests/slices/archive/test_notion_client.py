"""NotionClient — create_page over Notion's REST API."""

from __future__ import annotations

import httpx
import pytest
import respx

from newsletter.slices.archive.notion_client import (
    NotionClient,
    NotionError,
)


@respx.mock
def test_create_page_returns_page_id_on_success():
    create = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=httpx.Response(200, json={"id": "abc-123"})
    )
    client = NotionClient(token="secret", database_id="db-1")
    page_id = client.create_page(
        title="hello",
        properties={"Audience": {"select": {"name": "general"}}},
        children=[
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}}
        ],
    )
    assert page_id == "abc-123"
    assert create.called
    body = create.calls[0].request.read().decode()
    assert "db-1" in body
    assert "hello" in body
    assert create.calls[0].request.headers["Authorization"] == "Bearer secret"
    assert create.calls[0].request.headers["Notion-Version"] == "2022-06-28"


@respx.mock
def test_create_page_propagates_http_errors_as_notion_error():
    respx.post("https://api.notion.com/v1/pages").mock(
        return_value=httpx.Response(401, json={"message": "unauthorized"})
    )
    client = NotionClient(token="bad", database_id="db-1")
    with pytest.raises(NotionError) as exc:
        client.create_page(title="x", properties={}, children=[])
    assert "401" in str(exc.value)
    assert "unauthorized" in str(exc.value)


@respx.mock
def test_create_page_propagates_network_errors():
    respx.post("https://api.notion.com/v1/pages").mock(
        side_effect=httpx.ConnectError("boom")
    )
    client = NotionClient(token="secret", database_id="db-1")
    with pytest.raises(NotionError):
        client.create_page(title="x", properties={}, children=[])


@respx.mock
def test_create_page_payload_shape():
    create = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=httpx.Response(200, json={"id": "p1"})
    )
    client = NotionClient(token="secret", database_id="db-1", api_version="2099-01-01")
    client.create_page(
        title="My Title",
        properties={"Date": {"date": {"start": "2026-05-19"}}},
        children=[
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}}
        ],
    )
    import json

    body = json.loads(create.calls[0].request.read())
    assert body["parent"] == {"database_id": "db-1"}
    title_blob = body["properties"]["Name"]["title"]
    assert title_blob[0]["text"]["content"] == "My Title"
    assert body["properties"]["Date"] == {"date": {"start": "2026-05-19"}}
    assert body["children"][0]["type"] == "paragraph"
    headers = create.calls[0].request.headers
    assert headers["Notion-Version"] == "2099-01-01"


def test_from_settings_disabled_without_token(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "")
    monkeypatch.setenv("NOTION_DATABASE_ID", "")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()
    assert NotionClient.from_settings() is None


def test_from_settings_disabled_without_database_id(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret")
    monkeypatch.setenv("NOTION_DATABASE_ID", "")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()
    assert NotionClient.from_settings() is None


def test_from_settings_builds_client_when_both_set(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret")
    monkeypatch.setenv("NOTION_DATABASE_ID", "abc")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()
    client = NotionClient.from_settings()
    assert client is not None
    assert client.database_id == "abc"
