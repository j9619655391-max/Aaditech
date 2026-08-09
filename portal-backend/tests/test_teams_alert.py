"""Tests for the MS Teams alert channel (app/integrations/alerting.py).

`_send_teams` posts a classic MessageCard first, then falls back to the
Workflow (adaptive card) format — the first 2xx wins. These tests verify the
payload shapes and the fallback, with httpx fully stubbed (no network).
"""
import asyncio

import pytest

from app.integrations import alerting


def _run(coro):
    return asyncio.run(coro)


class _FakeResp:
    def __init__(self, status_code):
        self.status_code = status_code


def _stub_httpx(monkeypatch, responses):
    """responses: list of status codes returned for successive POSTs."""
    import httpx

    calls = []

    class _FakeClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            calls.append((url, json))
            return _FakeResp(responses[len(calls) - 1])

    monkeypatch.setattr(alerting.httpx, "AsyncClient", _FakeClient)
    return calls


def test_send_teams_disabled_when_no_webhook(monkeypatch):
    monkeypatch.setattr(alerting.settings, "teams_webhook_url", "")
    assert _run(alerting._send_teams("hi")) is False


def test_send_teams_uses_message_card_first(monkeypatch):
    monkeypatch.setattr(alerting.settings, "teams_webhook_url", "https://outlook.office.com/webhook/x")
    calls = _stub_httpx(monkeypatch, [200])
    assert _run(alerting._send_teams("disk full")) is True
    url, payload = calls[0]
    assert url == "https://outlook.office.com/webhook/x"
    assert payload["@type"] == "MessageCard"
    assert payload["text"] == "disk full"


def test_send_teams_falls_back_to_adaptive_card(monkeypatch):
    monkeypatch.setattr(alerting.settings, "teams_webhook_url", "https://outlook.office.com/webhook/x")
    # First (MessageCard) rejected, second (adaptive) accepted.
    calls = _stub_httpx(monkeypatch, [400, 202])
    assert _run(alerting._send_teams("alert")) is True
    assert calls[0][1]["@type"] == "MessageCard"
    assert calls[1][1]["type"] == "message"  # adaptive workflow format


def test_send_alert_ok_when_only_teams_works(monkeypatch):
    monkeypatch.setattr(alerting.settings, "teams_webhook_url", "https://outlook.office.com/webhook/x")
    monkeypatch.setattr(alerting.settings, "telegram_bot_token", "")
    monkeypatch.setattr(alerting.settings, "slack_webhook_url", "")
    _stub_httpx(monkeypatch, [200])
    result = _run(alerting.send_alert("down"))
    assert result["teams_delivered"] is True


def test_send_alert_raises_when_all_channels_fail(monkeypatch):
    monkeypatch.setattr(alerting.settings, "teams_webhook_url", "https://outlook.office.com/webhook/x")
    monkeypatch.setattr(alerting.settings, "telegram_bot_token", "123:tok")
    monkeypatch.setattr(alerting.settings, "telegram_chat_id", "-1")
    monkeypatch.setattr(alerting.settings, "slack_webhook_url", "https://hooks.slack.com/x")
    # All three channels fail (Telegram+Slack each one POST, Teams tries two).
    _stub_httpx(monkeypatch, [500, 500, 500, 500])
    with pytest.raises(alerting.AlertDeliveryError):
        _run(alerting.send_alert("down"))
