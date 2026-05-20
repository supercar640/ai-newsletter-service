"""SlackClient — POST a Block Kit card to an Incoming Webhook."""

from __future__ import annotations

import httpx
import pytest
import respx

from newsletter.slices.distribution.slack_client import SlackClient, SlackError

_WEBHOOK = "https://hooks.slack.com/services/T000/B000/XXXX"


@respx.mock
def test_post_sends_blocks_to_webhook():
    route = respx.post(_WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
    client = SlackClient(webhook_url=_WEBHOOK)
    client.post([{"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}])
    assert route.called
    body = route.calls[0].request.read().decode()
    assert "section" in body
    assert "blocks" in body


@respx.mock
def test_post_raises_on_http_error():
    respx.post(_WEBHOOK).mock(return_value=httpx.Response(403, text="invalid_token"))
    client = SlackClient(webhook_url=_WEBHOOK)
    with pytest.raises(SlackError) as exc:
        client.post([{"type": "section"}])
    assert "403" in str(exc.value)
    assert "invalid_token" in str(exc.value)


@respx.mock
def test_post_raises_on_network_error():
    respx.post(_WEBHOOK).mock(side_effect=httpx.ConnectError("boom"))
    client = SlackClient(webhook_url=_WEBHOOK)
    with pytest.raises(SlackError):
        client.post([{"type": "section"}])


def test_constructor_rejects_empty_url():
    with pytest.raises(ValueError):
        SlackClient(webhook_url="")


def test_from_settings_disabled_without_url(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()
    assert SlackClient.from_settings() is None


def test_from_settings_builds_client_when_set(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", _WEBHOOK)
    from newsletter.core.config import get_settings

    get_settings.cache_clear()
    client = SlackClient.from_settings()
    assert client is not None
