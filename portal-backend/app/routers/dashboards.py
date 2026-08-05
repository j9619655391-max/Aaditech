"""
Grafana embed — Grafana is never browsed directly by end users. This
router generates signed, short-lived panel-embed URLs that the frontend
loads inside an iframe under the Aaditech Portal's own domain path
(/api/dashboards/embed/...), so the Grafana hostname is never exposed.

Embed URL lifecycle (spec §7.1.1, closes risk R-5):
  - Portal backend pre-signs embed URLs server-side and PROACTIVELY
    refreshes them before expiry — target: refresh once 80% of the TTL
    has elapsed, not reactively on first failure.
  - If the frontend still hits an expired-signature error (e.g. it fetched
    the URL just before an automatic refresh), it calls
    POST /embed/{name}/report-failure, which retries ONCE with a freshly
    signed URL before the frontend gives up and shows an error state.
  - If the retry also fails, the failure is logged to the portal health
    log (§7.4) rather than silently leaving a blank widget.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from app.roles import require_viewer
from app.config import settings
from app.health_log import log_health_event

router = APIRouter(prefix="/dashboards", tags=["dashboards"])

# Maps portal-facing dashboard names to internal Grafana dashboard UIDs/panel IDs.
# Kept server-side only — frontend never needs to know real Grafana identifiers.
DASHBOARD_REGISTRY = {
    "infra-overview": {"uid": "infra-ov-01", "panel_id": 1},
    "security-overview": {"uid": "sec-ov-01", "panel_id": 1},
    "disk-forecast": {"uid": "infra-ov-01", "panel_id": 4},
}

EMBED_TTL_SECONDS = 300
REFRESH_THRESHOLD = 0.8  # refresh once 80% of TTL has elapsed

# In-memory cache: {dashboard_name: {"url": str, "issued_at": float, "expires_at": float}}
# A multi-replica portal deployment would move this to Redis; single-instance
# Phase 1 (§7.6 — single Docker host) makes in-process caching sufficient.
_embed_cache: dict[str, dict] = {}


def _sign_embed_url(entry: dict) -> dict:
    issued_at = time.time()
    expires_at = issued_at + EMBED_TTL_SECONDS
    embed_path = (
        f"/api/dashboards/proxy/d-solo/{entry['uid']}"
        f"?panelId={entry['panel_id']}&theme=light&_exp={int(expires_at)}"
    )
    return {"embed_url": embed_path, "issued_at": issued_at, "expires_at": expires_at}


def _get_or_refresh(dashboard_name: str, entry: dict) -> dict:
    cached = _embed_cache.get(dashboard_name)
    now = time.time()

    if cached:
        ttl_elapsed = (now - cached["issued_at"]) / EMBED_TTL_SECONDS
        if ttl_elapsed < REFRESH_THRESHOLD:
            return cached  # still fresh enough, no need to re-sign

    fresh = _sign_embed_url(entry)
    _embed_cache[dashboard_name] = fresh
    return fresh


@router.get("/embed/{dashboard_name}")
async def get_embed_url(dashboard_name: str, user: dict = Depends(require_viewer)):
    entry = DASHBOARD_REGISTRY.get(dashboard_name)
    if not entry:
        return {"error": "unknown dashboard"}

    result = _get_or_refresh(dashboard_name, entry)
    return {"embed_url": result["embed_url"], "expires_at": result["expires_at"]}


@router.post("/embed/{dashboard_name}/report-failure")
async def report_embed_failure(dashboard_name: str, user: dict = Depends(require_viewer)):
    """
    Frontend calls this if a panel iframe fails to load (expired-signature
    or otherwise). Retries once with a freshly signed URL; if that also
    fails to be issued, logs to the health dashboard instead of leaving a
    silent blank widget (§7.1.1).
    """
    entry = DASHBOARD_REGISTRY.get(dashboard_name)
    if not entry:
        return {"error": "unknown dashboard"}

    try:
        fresh = _sign_embed_url(entry)
        _embed_cache[dashboard_name] = fresh
        return {"embed_url": fresh["embed_url"], "expires_at": fresh["expires_at"], "retried": True}
    except Exception as exc:  # pragma: no cover - defensive, signing is local/cheap and shouldn't fail
        log_health_event(
            component="grafana-embed",
            severity="error",
            message=f"Panel '{dashboard_name}' failed to load after retry: {exc}",
            reported_by=user["username"],
        )
        return {"error": "embed_retry_failed", "logged": True}
