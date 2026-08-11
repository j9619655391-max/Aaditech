"""
GLPI REST API client.

Handles ticket creation/lookup and asset queries from within the
Aaditech Portal. Reference: https://github.com/glpi-project/glpi/blob/main/apirest.md
"""
from __future__ import annotations

import httpx
from typing import Any


class GLPIAuthError(Exception):
    pass


class GLPIClient:
    def __init__(self, base_url: str, app_token: str, user_token: str, timeout: float = 10.0,
                 verify: str | bool = True):
        self.base_url = base_url.rstrip("/")
        self.app_token = app_token
        self.user_token = user_token
        self.timeout = timeout
        self.verify = verify
        self._session_token: str | None = None

    async def _init_session(self, client: httpx.AsyncClient) -> str:
        headers = {
            "App-Token": self.app_token,
            "Authorization": f"user_token {self.user_token}",
        }
        resp = await client.get(f"{self.base_url}/initSession", headers=headers)
        if resp.status_code != 200:
            raise GLPIAuthError(f"GLPI initSession failed: {resp.status_code}")
        self._session_token = resp.json()["session_token"]
        return self._session_token

    def _headers(self) -> dict:
        return {"App-Token": self.app_token, "Session-Token": self._session_token or ""}

    async def create_ticket(self, title: str, description: str, urgency: int = 3,
                             category_id: int | None = None) -> dict[str, Any]:
        """Create a GLPI ticket. urgency: 1=Very Low .. 5=Very High."""
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify) as client:
            if not self._session_token:
                await self._init_session(client)
            payload = {
                "input": {
                    "name": title,
                    "content": description,
                    "urgency": urgency,
                    **({"itilcategories_id": category_id} if category_id else {}),
                }
            }
            resp = await client.post(f"{self.base_url}/Ticket", json=payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def get_ticket(self, ticket_id: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify) as client:
            if not self._session_token:
                await self._init_session(client)
            resp = await client.get(f"{self.base_url}/Ticket/{ticket_id}", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def list_open_tickets(self, limit: int = 50) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify) as client:
            if not self._session_token:
                await self._init_session(client)
            params = {"range": f"0-{limit - 1}", "searchText[status]": "1"}  # status 1 = New
            resp = await client.get(f"{self.base_url}/Ticket", headers=self._headers(), params=params)
            resp.raise_for_status()
            return resp.json()
