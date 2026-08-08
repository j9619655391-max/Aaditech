"""
Local username/password login (created by the one-click setup wizard).

Complements the Azure AD SSO flow (app/routers/auth_sso.py). A deployment can
authenticate with either path; the wizard's bootstrap admin uses this one. Both
paths hand out the same portal-scoped JWT via app/auth.create_access_token().
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import users
from app.auth import create_access_token

router = APIRouter(prefix="/auth/login", tags=["auth"])


@router.post("")
async def local_login(payload: dict):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    user = users.verify_credentials(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(user["username"], user["roles"])
    return {"access_token": token, "token_type": "bearer", "roles": user["roles"]}
