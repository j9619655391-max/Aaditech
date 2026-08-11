"""
Operational observability endpoints — the portal's own audit trail and
health-dashboard views (spec §7.4). Both storage modules already exist with
read() functions that were never exposed (finding 2.1/2.2); this router wires
them behind the viewer role so the frontend health/audit views have real data.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.roles import require_viewer
from app.audit import read_audit_entries
from app.health_log import read_health_events

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/audit")
async def audit_log(
    limit: int = Query(100, ge=1, le=1000),
    action: str | None = None,
    user: dict = Depends(require_viewer),
):
    """Recent audit entries (newest first), optionally filtered by action."""
    return read_audit_entries(limit=limit, action=action)


@router.get("/health")
async def health_log(
    limit: int = Query(100, ge=1, le=1000),
    severity: str | None = None,
    user: dict = Depends(require_viewer),
):
    """Recent operational/health events, optionally filtered by severity."""
    return read_health_events(limit=limit, severity=severity)