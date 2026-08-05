"""
Alerting backbone (spec §3.6).

Channel roles (do not conflate these — this is the design fix for risk R-1):

  Telegram / Slack   PRIMARY channel for ALL real-time, time-sensitive
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

import httpx

from app import ms_oauth
from app.config import settings


class AlertDeliveryError(Exception):
    """Raised only if BOTH Telegram and Slack fail — surfaced loudly since
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


async def send_alert(message: str, portal_link: str | None = None) -> dict:
    """
    Sends a time-sensitive alert through the primary backbone (Telegram AND
    Slack — both configured channels receive it, not either/or, for
    redundancy). Every alert should include a portal_link back to the
    persistent GLPI/portal entry (system-of-record role, §3.6).
    """
    full_message = message if not portal_link else f"{message}\n\nDetails: {portal_link}"

    telegram_ok = await _send_telegram(full_message)
    slack_ok = await _send_slack(full_message)

    if not telegram_ok and not slack_ok:
        raise AlertDeliveryError(
            "Both Telegram and Slack delivery failed — the alerting backbone itself "
            "may be down. This should itself trigger an escalation outside this system."
        )

    return {"telegram_delivered": telegram_ok, "slack_delivered": slack_ok}


async def send_report_email(subject: str, body: str, recipients: list[str]) -> bool:
    """
    Sends a SECONDARY-channel scheduled report/digest via Microsoft Graph
    (/sendMail). NEVER call this for time-sensitive alerts — use
    send_alert() instead (the O365 channel is independent of the Telegram/
    Slack primary backbone, so a failure here degrades reporting only).

    The HTTP/OAuth2 logic (client-credentials grant, stdlib-only) lives in
    app/ms_oauth.py so it's unit-testable offline. Requires infra/.env
    configuration from the Phase 0 Azure app registration spike (§6):
    AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID, plus an app
    registered with the `Mail.Send` application permission on the target
    tenant. With no config it returns False without making a network call.
    """
    if not ms_oauth.azure_configured():
        # Fails soft — this is explicitly NOT on the critical alerting path
        # (§3.6). No config => nothing to send.
        return False

    try:
        return ms_oauth.send_graph_email(subject, body, recipients)
    except Exception:
        # Reporting channel — a failure here is observable but not critical.
        return False
