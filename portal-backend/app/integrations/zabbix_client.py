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
    def __init__(self, base_url: str, api_token: str, timeout: float = 10.0,
                 verify: str | bool = True):
        self.base_url = base_url
        self.api_token = api_token
        self.timeout = timeout
        self.verify = verify
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
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify) as client:
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

    async def get_active_problems(self, min_severity: int = 2, recent: bool = True) -> list[dict]:
        """Fetch currently OPEN problems via problem.get (finding 5.2). This is
        the Zabbix-recommended call for active alerts — it returns one row per
        unresolved problem with the triggering severity, whereas trigger.get
        throws in suppressed/ACK-ed noise. Severity: 0=Not classified .. 5=Disaster."""
        return await self._call(
            "problem.get",
            {
                "output": ["eventid", "objectid", "name", "severity", "clock", "acknowledged"],
                # recent=1 restricts to problems where the last event is still
                # in a problem state — no resolved/closed entries.
                "recent": 1 if recent else 0,
                "min_severity": min_severity,
                "selectHosts": ["host"],
                "sortfield": ["severity", "eventid"],
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

    async def ensure_host_registered(self, host_name: str, visible_name: str | None = None) -> str:
        """Zabbix auto-registration (finding): ensure an agent-connected host
        exists. Auto-registration actions create the host server-side, but we
        make this idempotent so a fresh poller run can't break. Returns the
        (existing or newly created) host id."""
        existing = await self._call(
            "host.get",
            {
                "output": ["hostid"],
                "filter": {"host": [host_name]},
            },
        )
        if existing:
            return existing[0]["hostid"]
        created = await self._call(
            "host.create",
            {
                "host": host_name,
                "status": 0,  # monitored
                "interfaces": [
                    {
                        "type": 1,  # Zabbix agent
                        "main": 1,
                        "useip": 1,
                        "ip": "127.0.0.1",  # passive checks; data arrives via agent
                        "dns": "",
                        "port": "10050",
                    }
                ],
            },
        )
        return created["hostids"][0]
