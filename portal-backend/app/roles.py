"""
Portal RBAC role model (spec §7.1, v1.2/v1.4).

SSO (Azure AD) handles AUTHENTICATION only — proving who you are.
Authorization (what you're allowed to do inside the portal) is role-based
and defined here, independently of SSO. Roles are assignable per engineer
or per AD/Azure AD group (mapped during the SSO callback — see
app/routers/auth_sso.py TODO), and role membership changes are themselves
audit-logged (see app/audit.py).

Three roles are defined for Phase 1a (minimum viable set per spec):

  VIEWER            Read-only dashboards/alerts. No write actions anywhere.
  SUPPORT_ENGINEER   Everything Viewer can do, plus: ticketing (create/view
                     GLPI tickets), MeshCentral remote sessions, and
                     visibility into Category A auto-fix history. Cannot
                     approve Category B cleanup.
  CLEANUP_APPROVER   Everything Support Engineer can do, plus: the ability
                     to act on Category B "Approve & Execute" / "Restore
                     from quarantine" requests (§3.5). This is deliberately
                     a separate, narrower grant than general SSO login —
                     closes spec risk R-8 (undefined authorization model
                     for fleet-wide deletion actions).

Roles are NOT mutually exclusive tiers in the code (a user's `roles` list
in the JWT may contain more than one), but the intended assignment model
is additive as described above.
"""
from __future__ import annotations

from enum import StrEnum

from fastapi import Depends, HTTPException

from app.auth import get_current_user


class Role(StrEnum):
    VIEWER = "viewer"
    SUPPORT_ENGINEER = "support_engineer"
    CLEANUP_APPROVER = "cleanup_approver"


def require_any_role(*allowed: Role):
    """Dependency factory: allows the request if the user holds ANY of the given roles."""

    async def _checker(user: dict = Depends(get_current_user)) -> dict:
        user_roles = set(user.get("roles", []))
        if not user_roles.intersection({r.value for r in allowed}):
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {', '.join(r.value for r in allowed)}",
            )
        return user

    return _checker


# Convenience dependencies matching the spec's named roles directly.
require_viewer = require_any_role(Role.VIEWER, Role.SUPPORT_ENGINEER, Role.CLEANUP_APPROVER)
require_support_engineer = require_any_role(Role.SUPPORT_ENGINEER, Role.CLEANUP_APPROVER)
require_cleanup_approver = require_any_role(Role.CLEANUP_APPROVER)
