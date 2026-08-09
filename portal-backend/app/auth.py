"""
Portal authentication.

End users log in ONCE at the portal (via Azure AD / AD SSO in production —
see docs/DEPLOYMENT.md for the Azure AD app registration steps). This
module issues a portal-scoped JWT after SSO callback; that JWT is what
protects every /api/* route. The portal backend then uses ITS OWN service
credentials (from config.py) to talk to Wazuh/Zabbix/GLPI/MeshCentral —
the end user's identity/token is never forwarded to those systems.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

security = HTTPBearer()


def create_access_token(subject: str, roles: list[str]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiry_minutes)
    payload = {"sub": subject, "roles": roles, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_service_token(subject: str, roles: list[str], expiry_days: int = 365) -> str:
    """A long-lived machine token (agent pollers, cron jobs). Scoped to the
    same JWT role model as user sessions, so existing require_* dependencies
    work unchanged — the difference is only the expiry."""
    expire = datetime.now(timezone.utc) + timedelta(days=expiry_days)
    payload = {"sub": subject, "roles": roles, "exp": expire, "service": True}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
        ) from exc


async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    payload = decode_access_token(creds.credentials)
    return {"username": payload["sub"], "roles": payload.get("roles", [])}


def require_role(role: str):
    async def _checker(user: dict = Depends(get_current_user)) -> dict:
        if role not in user["roles"]:
            raise HTTPException(status_code=403, detail=f"Requires role: {role}")
        return user

    return _checker
