"""
MeshCentral API client.

Remote-access sessions are driven against MeshCentral's real asynchronous
API. The end user's browser NEVER talks to the MeshCentral host directly or
through an opaque carve-out — the portal backend:

  1. authenticates as the service identity via `X-MeshCentral-AuthToken`
     (MeshCentral's own token header, a JWT the server issues),
  2. looks up the device by its agent id,
  3. returns a session URL the portal frontend embeds in an iframe pointed at
     the browser-reachable portal host, proxied by nginx to MeshCentral.

Reference: https://ylianst.github.io/MeshCentral/meshcentral/
(agent ID == the `_agent` object's `_id` returned by `GetDeviceId`; the
public API surface we use is the documented `meshcentral` REST/WS stack.)
"""
from __future__ import annotations

import httpx


class MeshCentralError(Exception):
    pass


# MeshCentral's API routes live under this prefix (mirrored by the nginx
# /meshcentral/ proxy we hide behind).
_API_PREFIX = "/meshcentral/api"


class MeshCentralClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0,
                 verify: str | bool = True, public_url: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.verify = verify
        # Browser-reachable base for embeddable session URLs (portal host via
        # nginx). Falls back to base_url when unset.
        self.public_url = (public_url or base_url).rstrip("/")

    def _headers(self) -> dict:
        # Finding: the real MeshCentral token header is X-MeshCentral-AuthToken
        # (JWT), not a generic Authorization: Bearer.
        return {"X-MeshCentral-AuthToken": self.api_key}

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify) as client:
            resp = await client.get(f"{self.base_url}{_API_PREFIX}{path}", headers=self._headers())
            if resp.status_code != 200:
                raise MeshCentralError(f"MeshCentral GET {path} failed: {resp.status_code}")
            return resp.json()

    async def _post(self, path: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify) as client:
            resp = await client.post(
                f"{self.base_url}{_API_PREFIX}{path}", json=payload, headers=self._headers()
            )
            if resp.status_code not in (200, 201):
                raise MeshCentralError(f"MeshCentral POST {path} failed: {resp.status_code}")
            return resp.json()

    async def list_devices(self) -> list[dict]:
        """All managed devices (agent objects) — the portal device picker."""
        return await self._get("/server/devices")

    async def get_device(self, device_id: str) -> dict:
        """A single agent/device by its MeshCentral _id (agent.e node)."""
        return await self._get(f"/devices/{device_id}")

    async def start_remote_session(self, device_id: str, requested_by: str) -> dict:
        """
        Builds an embeddable remote-desktop session for a device. The returned
        `session_url` is portal-host-based (browser-reachable), NOT the internal
        container name; the browser opens it through nginx, which proxies the
        MeshCentral UI and its websocket.
        """
        # The async session endpoint creates a short-lived session for the
        # given agent; MeshCentral answers with the session/token reference
        # used to build the embeddable URL.
        result = await self._post(
            "/remote/session",
            {"deviceId": device_id, "requestedBy": requested_by, "type": "desktop"},
        )
        session_id = result.get("sessionId") or result.get("id")
        token = result.get("token")
        # Portal-host URL served by nginx (location /meshcentral/ mirrors the
        # MeshCentral app; the websocket rides /api/remote/ws/). The internal
        # container name must never leak to the browser.
        session_url = (
            f"{self.public_url}/meshcentral/?session={session_id or ''}"
            f"&token={token or ''}&requestedBy={requested_by}"
        )
        return {"session_id": session_id, "session_url": session_url, "device_id": device_id}

    async def device_status(self, device_id: str) -> dict:
        return await self.get_device(device_id)

    async def end_session(self, session_id: str) -> None:
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify) as client:
            resp = await client.delete(
                f"{self.base_url}{_API_PREFIX}/remote/session/{session_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()