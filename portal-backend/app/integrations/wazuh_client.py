"""
Wazuh API client.

Surfaces security alerts, File Integrity Monitoring (FIM) events, and
CVE/vulnerability findings into the Aaditech Portal. This is the ONLY
place in the codebase that talks to Wazuh directly — no other module
and no frontend code ever calls Wazuh's API or dashboard URL.

Wazuh REST API docs (for reference when deploying against a real
manager): https://documentation.wazuh.com/current/user-manual/api/reference.html
"""
from __future__ import annotations

import httpx
from typing import Any


class WazuhAuthError(Exception):
    """Raised when Wazuh API authentication fails."""


class WazuhClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: float = 10.0,
                 verify: str | bool = True):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.verify = verify
        self._token: str | None = None

    async def _authenticate(self, client: httpx.AsyncClient) -> str:
        """Wazuh uses short-lived JWT tokens obtained via basic auth on /security/user/authenticate."""
        resp = await client.post(
            f"{self.base_url}/security/user/authenticate",
            auth=(self.username, self.password),
        )
        if resp.status_code != 200:
            raise WazuhAuthError(f"Wazuh authentication failed: {resp.status_code}")
        data = resp.json()
        token = data.get("data", {}).get("token")
        if not token:
            raise WazuhAuthError("Wazuh authentication response missing token")
        self._token = token
        return token

    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(verify=self.verify, timeout=self.timeout) as client:
            if not self._token:
                await self._authenticate(client)
            headers = {"Authorization": f"Bearer {self._token}"}
            resp = await client.get(f"{self.base_url}{path}", headers=headers, params=params)
            if resp.status_code == 401:
                # token expired — re-authenticate once and retry
                await self._authenticate(client)
                headers = {"Authorization": f"Bearer {self._token}"}
                resp = await client.get(f"{self.base_url}{path}", headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_alerts(self, limit: int = 50, level_min: int | None = None) -> list[dict]:
        """Fetch recent security alerts, optionally filtered by minimum severity level."""
        params: dict[str, Any] = {"limit": limit, "sort": "-timestamp"}
        data = await self._get("/alerts", params=params)
        alerts = data.get("data", {}).get("affected_items", [])
        if level_min is not None:
            alerts = [a for a in alerts if a.get("rule", {}).get("level", 0) >= level_min]
        return alerts

    async def get_fim_events(self, agent_id: str | None = None, limit: int = 50) -> list[dict]:
        """Fetch File Integrity Monitoring events, optionally scoped to one agent."""
        path = f"/syscheck/{agent_id}" if agent_id else "/syscheck"
        data = await self._get(path, params={"limit": limit})
        return data.get("data", {}).get("affected_items", [])

    async def get_vulnerabilities(self, agent_id: str | None = None, limit: int = 50) -> list[dict]:
        """Fetch CVE/vulnerability findings from the Vulnerability Detector module."""
        path = f"/vulnerability/{agent_id}" if agent_id else "/vulnerability"
        data = await self._get(path, params={"limit": limit})
        return data.get("data", {}).get("affected_items", [])

    async def get_agent_status_summary(self) -> dict[str, int]:
        """Fleet-wide agent connection status summary — used for the agent health widget."""
        data = await self._get("/agents/summary/status")
        return data.get("data", {})

    async def get_agents_with_versions(self, limit: int = 500) -> list[dict]:
        """
        Per-agent version info for the fleet (spec §7.2.1 — agent version/patch
        drift visibility). Returns agent id, name, connection status, and
        installed Wazuh agent version, for the portal's agent health dashboard.
        """
        data = await self._get(
            "/agents",
            params={"limit": limit, "select": "id,name,status,version"},
        )
        return data.get("data", {}).get("affected_items", [])
