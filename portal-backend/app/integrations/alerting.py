"""
Alerting backbone (spec §3.6).

Channel roles (do not conflate these — this is the design fix for risk R-1):

  Telegram / Slack / MS Teams   PRIMARY channel for ALL real-time, time-sensitive
                      alerts (Wazuh security events, Zabbix threshold
                      triggers, SLA escalation tiers, agent offline
                      notices). Independent of O365/Azure AD — keeps
                      working during a full Exchange Online or Azure AD
                      outage.

  Email (O365 SMTP)   SECONDARY/reporting channel only: scheduled digests,
                      weekly/monthly reports, non-urgent notifications.
                      NOT used for time-sensitive alerts. If Azure app
                      registration/token fails, only reporting degrades —
                      real-time alerting is unaffected.

  GLPI dashboard      Not a live channel — system of record. Every
                      push/email notification should link back to a
                      persistent portal/GLPI entry for after-the-fact
                      review and audit.

`send_alert()` is the ONLY function other modules should call for
time-sensitive notifications — it enforces the primary-channel-first
behavior itself so callers can't accidentally reach for email on the
critical path.
"""
from __future__ import annotations

import smtplib
import ssl
from email.mime.text import MIMEText

import httpx

from app.config import settings


class AlertDeliveryError(Exception):
    """Raised only if ALL primary channels fail — surfaced loudly since
    this means the primary alerting backbone itself is down."""


async def _send_telegram(message: str) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json={"chat_id": settings.telegram_chat_id, "text": message})
        return resp.status_code == 200


async def _send_slack(message: str) -> bool:
    if not settings.slack_webhook_url:
        return False
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(settings.slack_webhook_url, json={"text": message})
        return resp.status_code == 200


async def _send_teams(message: str) -> bool:
    """POST an alert to a Microsoft Teams incoming webhook.

    Accepts both the classic Connector MessageCard payload and the newer
    Workflow webhook format (adaptive card) — the first 2xx wins, so either
    webhook style works.
    """
    if not settings.teams_webhook_url:
        return False

    message_card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": message,
        "text": message,
    }
    adaptive = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [{"type": "TextBlock", "text": message, "wrap": True}],
                },
            }
        ],
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for payload in (message_card, adaptive):
            try:
                resp = await client.post(settings.teams_webhook_url, json=payload)
                if resp.status_code in (200, 201, 202):
                    return True
            except httpx.HTTPError:
                continue
    return False


async def send_alert(message: str, portal_link: str | None = None) -> dict:
    """
    Sends a time-sensitive alert through the primary backbone (Telegram AND
    Slack AND MS Teams — every configured channel receives it, not either/or,
    for redundancy). Every alert should include a portal_link back to the
    persistent GLPI/portal entry (system-of-record role, §3.6).
    """
    full_message = message if not portal_link else f"{message}\n\nDetails: {portal_link}"

    telegram_ok = await _send_telegram(full_message)
    slack_ok = await _send_slack(full_message)
    teams_ok = await _send_teams(full_message)

    if not telegram_ok and not slack_ok and not teams_ok:
        raise AlertDeliveryError(
            "All primary channels (Telegram, Slack, MS Teams) failed — the alerting "
            "backbone itself may be down. This should itself trigger an escalation "
            "outside this system."
        )

    return {"telegram_delivered": telegram_ok, "slack_delivered": slack_ok, "teams_delivered": teams_ok}


def smtp_configured() -> bool:
    """True when the setup wizard has configured an SMTP email channel."""
    return bool(settings.smtp_host and settings.smtp_username and settings.smtp_from_address)


def send_smtp_email(subject: str, body: str, recipients: list[str]) -> bool:
    """
    Sends an email over SMTP using the credentials the one-click setup wizard
    collected (host/port/TLS from the provider preset, plus username/password).
    Returns True on success; never raises — the caller treats email as the
    secondary/reporting channel.
    """
    if not smtp_configured():
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_address
    msg["To"] = ", ".join(recipients)

    try:
        context = ssl.create_default_context()
        if settings.smtp_use_tls == "ssl":
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=15) as server:
                server.login(settings.smtp_username, settings.smtp_password)
                server.sendmail(settings.smtp_from_address, recipients, msg.as_string())
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                if settings.smtp_use_tls == "starttls":
                    server.starttls(context=context)
                server.login(settings.smtp_username, settings.smtp_password)
                server.sendmail(settings.smtp_from_address, recipients, msg.as_string())
        return True
    except Exception:
        # Reporting channel — a failure here is observable but not critical.
        return False
