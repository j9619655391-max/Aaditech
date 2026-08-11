"""
SSO login flow (Azure AD / Microsoft 365).

This is the ONLY place a user enters credentials — at Microsoft's login
page, never inside the portal itself. On successful SSO callback, we
issue our own portal-scoped JWT (see app/auth.py) and redirect back to
the frontend with it. Wazuh/Zabbix/GLPI/MeshCentral never see this token
or the user's Microsoft identity — the portal backend uses its own
service credentials for those.

The OAuth2 exchange logic (url construction, token exchange, id_token
decoding, group→role mapping) lives in app/ms_oauth.py (stdlib-only, so it
is unit-testable offline). This module is the HTTP layer: it builds the
redirects and issues the JWT.

Production setup required (see docs/DEPLOYMENT.md § Office 365 / Azure AD):
  1. Register an app in Azure AD, note Client ID / Tenant ID / Client Secret
  2. Set redirect URI to https://portal.aaditech.local/api/auth/sso/callback
  3. Populate AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID in infra/.env
  4. Optional: AZURE_ADMIN_GROUP_IDS (comma-separated group object IDs) whose
     members become CLEANUP_APPROVER at login (§7.1).
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app import ms_oauth
from app.auth import create_access_token
from app.config import settings

router = APIRouter(prefix="/auth/sso", tags=["auth"])

# OAuth2 state lives server-side keyed by a short-lived cookie/param value so
# the callback can't be CSRF-confused. The value doubles as the id_token
# `nonce` the callback must verify (replay protection). In-memory dict is fine
# for Phase 1 (single-instance) — same caveat as the other stores.
_state_cache: dict[str, str] = {}


def _base_url(request: Request) -> str:
    """Derive the deployment's public base URL from the incoming request so
    the Azure redirect_uri matches however the portal is reached (DNS name OR
    bare IP — the wizard is entirely IP-based). Falls back to the host header,
    then SERVER_NAME, then the documented default."""
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        return f"https://{forwarded_host}"
    host = request.headers.get("host")
    if host:
        return f"https://{host}"
    return ms_oauth.PORTAL_BASE_URL


@router.get("/login")
async def sso_login(request: Request):
    """Redirects the user to Microsoft's OAuth2 login page."""
    if not ms_oauth.azure_configured():
        return RedirectResponse(url="/login?error=azure_not_configured")

    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    _state_cache[state] = nonce
    return RedirectResponse(
        url=ms_oauth.build_authorize_url(state, base_url=_base_url(request), nonce=nonce)
    )


@router.get("/callback")
async def sso_callback(request: Request, code: str | None = None, state: str | None = None):
    """
    Handles Microsoft's OAuth2 redirect back to us. Exchanges the
    authorization `code` for user identity, then issues our own portal JWT.
    """
    if not code:
        return RedirectResponse(url="/login?error=missing_code")

    # CSRF: reject unknown/absent state. Pop once so a state value can't be replayed.
    expected_nonce = _state_cache.pop(state, None)
    if not state or expected_nonce is None:
        return RedirectResponse(url="/login?error=invalid_state")

    if not ms_oauth.azure_configured():
        return RedirectResponse(url="/login?error=azure_not_configured")

    try:
        tokens = ms_oauth.exchange_code_for_tokens(code, base_url=_base_url(request))
        # Finding 3.3: cryptographically verify the id_token (signature via
        # the tenant's JWKS, audience, issuer, expiry) and the nonce we minted
        # in /login before trusting any claim for identity or role mapping.
        claims = ms_oauth.verify_id_token(tokens["id_token"], nonce=expected_nonce)
    except Exception:
        # Any network/token error lands the user on a login error page.
        return RedirectResponse(url="/login?error=sso_exchange_failed")

    verified_username = (
        claims.get("email") or claims.get("preferred_username") or "unknown"
    )
    roles = ms_oauth.roles_from_claims(claims)
    token = create_access_token(subject=verified_username, roles=roles)
    # Deliver the JWT as a URL FRAGMENT (#), never a query param (?) — fragments
    # are not sent to the server, so the token never lands in proxy/access logs
    # or the Referer header (finding H8).
    return RedirectResponse(url=f"/login#token={token}")