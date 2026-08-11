"""Security alerts, FIM events, and vulnerability findings — backed by Wazuh."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.roles import require_viewer
from app.config import settings
from app.integrations.wazuh_client import WazuhClient
from app.integrations.version_drift import check_version_drift, summarize_drift
from app.integrations.pilot_ring import plan_rollout, summarize_rollout
from app.integrations.alerting import send_alert
from datetime import datetime

router = APIRouter(prefix="/alerts", tags=["alerts"])


def get_wazuh_client() -> WazuhClient:
    return WazuhClient(
        base_url=settings.wazuh_api_url,
        username=settings.wazuh_api_user,
        password=settings.wazuh_api_password,
        verify=settings.tls_verify(),
    )


@router.get("/")
async def list_alerts(
    limit: int = Query(50, le=500),
    level_min: int | None = None,
    user: dict = Depends(require_viewer),
):
    client = get_wazuh_client()
    return await client.get_alerts(limit=limit, level_min=level_min)


@router.get("/fim")
async def list_fim_events(
    agent_id: str | None = None,
    limit: int = Query(50, le=500),
    user: dict = Depends(require_viewer),
):
    client = get_wazuh_client()
    return await client.get_fim_events(agent_id=agent_id, limit=limit)


@router.get("/vulnerabilities")
async def list_vulnerabilities(
    agent_id: str | None = None,
    limit: int = Query(50, le=500),
    user: dict = Depends(require_viewer),
):
    client = get_wazuh_client()
    return await client.get_vulnerabilities(agent_id=agent_id, limit=limit)


@router.get("/agent-health")
async def agent_health_summary(user: dict = Depends(require_viewer)):
    client = get_wazuh_client()
    return await client.get_agent_status_summary()


@router.get("/agent-versions")
async def agent_version_drift(
    expected_version: str = Query(..., description="Current manager/expected agent version, e.g. v4.9.0"),
    notify_if_stale: bool = Query(False),
    user: dict = Depends(require_viewer),
):
    """
    Per-agent version drift report (§7.2.1). If notify_if_stale=true and any
    agent is beyond the mismatch threshold, pushes a summary through the
    alerting backbone (§3.6) rather than relying on manual audit.
    """
    client = get_wazuh_client()
    agents = await client.get_agents_with_versions()
    results = check_version_drift(agents, expected_version=expected_version)
    summary = summarize_drift(results)

    if notify_if_stale and summary["stale_agents"] > 0:
        await send_alert(
            f"[Agent Version Drift] {summary['stale_agents']} of {summary['total_agents']} "
            f"agents are more than 2 minor versions behind {expected_version}: "
            f"{', '.join(summary['stale_agent_names'])}"
        )

    return {"summary": summary, "agents": [r.__dict__ for r in results]}


@router.get("/rollout-plan")
async def agent_rollout_plan(
    pilot_started_at: str | None = Query(
        None, description="ISO timestamp the pilot ring push started, or omit if not yet pushed"
    ),
    expected_version: str = Query(..., description="Version being rolled out, for the pilot regression check"),
    pilot_percent: int = Query(10, ge=0, le=100),
    bake_period_hours: int = Query(48, ge=0),
    user: dict = Depends(require_viewer),
):
    """
    Phased rollout decision (§7.2.1): tells the GPO/Intune push automation
    which endpoints are eligible for `expected_version` right now — pilot
    ring immediately, fleet only after the bake period AND a clean pilot
    (no version-drift/failure signal on pilot agents, per version_drift.py).
    """
    client = get_wazuh_client()
    agents = await client.get_agents_with_versions()
    endpoint_ids = [a["id"] for a in agents]

    pilot_stale = 0
    if pilot_started_at:
        drift_results = check_version_drift(agents, expected_version=expected_version)
        # Only count drift among agents actually in the pilot ring as a
        # regression signal — fleet agents haven't been pushed yet, so their
        # "drift" from expected_version is expected, not a pilot regression.
        from app.integrations.pilot_ring import Ring, assign_ring

        pilot_ids = {eid for eid in endpoint_ids if assign_ring(eid, pilot_percent) == Ring.PILOT}
        pilot_stale = sum(1 for r in drift_results if r.agent_id in pilot_ids and r.is_stale)

    started_at = datetime.fromisoformat(pilot_started_at) if pilot_started_at else None
    decisions = plan_rollout(
        endpoint_ids,
        pilot_started_at=started_at,
        now=datetime.now(started_at.tzinfo if started_at else None),
        pilot_percent=pilot_percent,
        bake_period_hours=bake_period_hours,
        pilot_stale_agents=pilot_stale,
    )
    return summarize_rollout(decisions)
