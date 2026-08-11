"""Infrastructure/network performance metrics — backed by Zabbix."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.roles import require_viewer
from app.config import settings
from app.integrations.zabbix_client import ZabbixClient

router = APIRouter(prefix="/metrics", tags=["metrics"])


def get_zabbix_client() -> ZabbixClient:
    return ZabbixClient(
        base_url=settings.zabbix_api_url,
        api_token=settings.zabbix_api_token,
        verify=settings.tls_verify(),
    )


@router.get("/hosts")
async def list_hosts(user: dict = Depends(require_viewer)):
    client = get_zabbix_client()
    return await client.get_host_status()


@router.get("/triggers")
async def active_triggers(
    min_severity: int = Query(2, ge=0, le=5),
    user: dict = Depends(require_viewer),
):
    client = get_zabbix_client()
    # Finding 5.2: use problem.get (open problems) — trigger.get returns
    # suppressed/ACK-ed noise and flag-based attach rows, not a clean list of
    # things that are actually wrong right now.
    return await client.get_active_problems(min_severity=min_severity)


@router.get("/items/{item_id}/history")
async def item_history(
    item_id: str,
    limit: int = Query(100, le=1000),
    user: dict = Depends(require_viewer),
):
    client = get_zabbix_client()
    return await client.get_item_history(item_id, limit=limit)
