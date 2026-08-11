"""
Local username/password login (created by the one-click setup wizard).

Complements the Azure AD SSO flow (app/routers/auth_sso.py). A deployment can
authenticate with either path; the wizard's bootstrap admin uses this one. Both
paths hand out the same portal-scoped JWT via app/auth.create_access_token().
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from app import users
from app.auth import create_access_token
from app.config import settings

router = APIRouter(prefix="/auth/login", tags=["auth"])

# Simple in-memory brute-force guard (finding 3.5): after N failed attempts for
# a given identity (username + client IP), reject further attempts for a window.
# In-memory is acceptable for the single-instance deployment; note the same
# caveat as the other stores (lost on restart).
MAX_FAILED_ATTEMPTS = 5
FAILURE_WINDOW_SECONDS = 60 * 15
_failures: dict[str, list[float]] = {}


def _is_locked(identity: str) -> bool:
    now = time.time()
    stamps = [ts for ts in _failures.get(identity, []) if now - ts < FAILURE_WINDOW_SECONDS]
    _failures[identity] = stamps
    return len(stamps) >= MAX_FAILED_ATTEMPTS


@router.post("")
async def local_login(payload: dict, request: Request):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    identity = f"{username}|{request.client.host if request.client else 'unknown'}"

    if _is_locked(identity):
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts; try again later",
        )

    user = users.verify_credentials(username, password)
    if not user:
        _failures.setdefault(identity, []).append(time.time())
        raise HTTPException(status_code=401, detail="Invalid username or password")
    # Successful login clears the failure history for this identity.
    _failures.pop(identity, None)

    token = create_access_token(user["username"], user["roles"])
    return {"access_token": token, "token_type": "bearer", "roles": user["roles"]}
