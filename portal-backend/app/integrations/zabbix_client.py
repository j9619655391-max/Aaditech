"""
Zabbix API client (JSON-RPC).

Surfaces host status, active triggers, and performance graph data into
the Aaditech Portal. Reference: https://www.zabbix.com/documentation/current/en/manual/api
"""
from __future__ import annotations

import httpx
from typing import Any


class ZabbixAPIError(Exception):
    """Raised when the Zabbix JSON-RPC API returns an error object."""


class ZabbixClient:
    def __init__(self, base_url: str, api_token: str, timeout: float = 10.0):
        self.base_url = base_url
        self.api_token = api_token
        self.timeout = timeout
        self._request_id = 0

    async def _call(self, method: str, params: dict[str, Any]) -> Any:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._request_id,
        }
        headers = {
            "Content-Type": "application/json-rpc",
            "Authorization": f"Bearer {self.api_token}",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(self.base_url, json=payload, headers=headers)
            resp.raise_for_status()
            body = resp.json()
            if "error" in body:
                raise ZabbixAPIError(f"Zabbix API error: {body['error']}")
            return body.get("result")

    async def get_host_status(self) -> list[dict]:
        """Returns all monitored hosts with their availability status."""
        return await self._call(
            "host.get",
            {"output": ["hostid", "host", "status", "available"]},
        )

    async def get_active_triggers(self, min_severity: int = 2) -> list[dict]:
        """Fetch currently active (problem-state) triggers at or above a severity level.
        Severity scale: 0=Not classified .. 5=Disaster."""
        return await self._call(
            "trigger.get",
            {
                "output": ["triggerid", "description", "priority", "lastchange"],
                "filter": {"value": 1},
                "min_severity": min_severity,
                "selectHosts": ["host"],
                "sortfield": "priority",
                "sortorder": "DESC",
            },
        )

    async def get_item_history(self, item_id: str, limit: int = 100) -> list[dict]:
        """Fetch recent history points for a metric item (e.g., CPU%, disk I/O) for graphing."""
        return await self._call(
            "history.get",
            {
                "itemids": item_id,
                "history": 0,  # numeric float
                "sortfield": "clock",
                "sortorder": "DESC",
                "limit": limit,
            },
        )

    async def get_disk_forecast(self, item_id: str) -> dict:
        """Wraps Zabbix trend-forecasting; returns estimated time-until-threshold for a disk item."""
        # In production this triggers a calculated item / expression using Zabbix's
        # timeleft() function server-side. Placeholder shape documented for frontend contract.
        history = await self.get_item_history(item_id, limit=50)
        return {"item_id": item_id, "history_points": len(history), "forecast": "see calculated item"}
