"""
MeshCentral API client.

Triggers remote-access sessions and returns a portal-embeddable session
URL/token. The end user never sees the MeshCentral host directly — the
frontend embeds the session using the token this client returns.
Reference: https://ylianst.github.io/MeshCentral/meshcentral/
"""
from __future__ import annotations

import httpx


class MeshCentralError(Exception):
    pass


class MeshCentralClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def start_remote_session(self, device_id: str, requested_by: str) -> dict:
        """
        Requests a short-lived remote desktop session token for a device.
        The returned `session_url` is embedded in the portal's iframe/WebSocket
        proxy — never handed to the end user as a direct MeshCentral link.
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"deviceId": device_id, "requestedBy": requested_by, "type": "desktop"}
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            resp = await client.post(f"{self.base_url}/api/sessions", json=payload, headers=headers)
            if resp.status_code != 200:
                raise MeshCentralError(f"Failed to start session: {resp.status_code} {resp.text}")
            return resp.json()

    async def get_device_status(self, device_id: str) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            resp = await client.get(f"{self.base_url}/api/devices/{device_id}", headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def end_session(self, session_id: str) -> None:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            resp = await client.delete(f"{self.base_url}/api/sessions/{session_id}", headers=headers)
            resp.raise_for_status()
