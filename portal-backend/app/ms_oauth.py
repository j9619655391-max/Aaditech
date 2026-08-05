"""
Microsoft / Azure AD OAuth2 helpers (SSO + Graph email) implemented with
Python stdlib only (`urllib`).

Keeping these in a dependency-free module means they can be unit-tested in
an offline sandbox that has no fastapi/httpx/msal installed — the router
(app/routers/auth_sso.py) and alerting (app/integrations/alerting.py)
delegate to this module.

At runtime Microsoft is only contacted when the Azure settings
(AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID) are configured;
with no config every function that would need a token returns None/False.
"""
from __future__ import annotations

import base64
import json
import secrets
import urllib.parse
import urllib.request

AUTHORITY = "https://login.microsoftonline.com"
GRAPH_MAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
PORTAL_BASE_URL = "https://portal.aaditech.local"


class _LazySettings:
    """Defer importing app.config (and thus pydantic_settings) until a value
    is actually read, so this module can be unit-tested offline without
    fastapi/pydantic installed. In normal operation it just forwards to the
    real settings object; tests patch `app.ms_oauth.settings`."""

    def __getattr__(self, name: str):
        from app.config import settings

        return getattr(settings, name)


settings = _LazySettings()


# ---------------------------------------------------------------------------
# SSO (authorization-code grant)
# ---------------------------------------------------------------------------

def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.azure_client_id,
        "response_type": "code",
        "redirect_uri": f"{PORTAL_BASE_URL}/api/auth/sso/callback",
        "scope": "openid profile email",
        "state": state,
        "nonce": secrets.token_urlsafe(16),
        "response_mode": "query",
    }
    return f"{AUTHORITY}/{settings.azure_tenant_id}/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"


def decode_id_token(id_token: str) -> dict:
    """Decode an id_token's JWT payload (claims). Signature verification is
    deferred to the platform's identity stack; the claims we read here are
    non-authoritative UI-level hints plus the group enumeration used for
    role mapping."""
    payload = id_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def roles_from_claims(claims: dict) -> list[str]:
    """Map an Azure AD id_token's claims to portal roles (§7.1).

    Any authenticated user is VIEWER + SUPPORT_ENGINEER. Users whose Azure
    AD group is in AZURE_ADMIN_GROUP_IDS additionally get CLEANUP_APPROVER.
    """
    roles = {"viewer", "support_engineer"}
    admin_groups = {
        g.strip() for g in (settings.azure_admin_group_ids or "").split(",") if g.strip()
    }
    if admin_groups:
        user_groups = set(claims.get("groups", []) or [])
        if user_groups & admin_groups:
            roles.add("cleanup_approver")
    return sorted(roles)


def exchange_code_for_tokens(code: str) -> dict:
    """POST an authorization code to the v2.0 token endpoint (uses the app's
    client secret). Returns the raw token response."""
    body = urllib.parse.urlencode({
        "client_id": settings.azure_client_id,
        "client_secret": settings.azure_client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": f"{PORTAL_BASE_URL}/api/auth/sso/callback",
        "scope": "openid profile email",
    }).encode("utf-8")
    token_url = f"{AUTHORITY}/{settings.azure_tenant_id}/oauth2/v2.0/token"
    req = urllib.request.Request(token_url, data=body, method="POST")
    with urllib.request.urlopen(req) as resp:  # noqa: S310 - https URL from config
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# O365 email (client-credentials grant → Graph /sendMail)
# ---------------------------------------------------------------------------

def _bearer_token() -> str:
    """App-only (client-credentials) access token for Microsoft Graph."""
    body = urllib.parse.urlencode({
        "client_id": settings.azure_client_id,
        "client_secret": settings.azure_client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }).encode("utf-8")
    token_url = f"{AUTHORITY}/{settings.azure_tenant_id}/oauth2/v2.0/token"
    req = urllib.request.Request(token_url, data=body, method="POST")
    with urllib.request.urlopen(req) as resp:  # noqa: S310 - https URL from config
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["access_token"]


def azure_configured() -> bool:
    return bool(
        settings.azure_client_id
        and settings.azure_client_secret
        and settings.azure_tenant_id
    )


def send_graph_email(subject: str, body: str, recipients: list[str]) -> bool:
    """Send an HTML email via Microsoft Graph /sendMail as the repo service
    account. Returns True on 202 Accepted. Caller decides how to handle
    unconfigured / failure cases."""
    if not azure_configured():
        return False

    message = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body},
            "toRecipients": [{"emailAddress": {"address": r}} for r in recipients],
        },
        "saveToSentItems": "true",
    }
    req = urllib.request.Request(
        GRAPH_MAIL_URL,
        data=json.dumps(message).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {_bearer_token()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310 - https URL to Microsoft
        return resp.status == 202