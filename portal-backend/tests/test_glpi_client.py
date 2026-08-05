"""Unit tests for GLPIClient. Run with: pytest tests/test_glpi_client.py"""
import pytest
import respx
from httpx import Response

from app.integrations.glpi_client import GLPIAuthError, GLPIClient

BASE_URL = "http://glpi:80/apirest.php"


@pytest.mark.asyncio
@respx.mock
async def test_create_ticket_initializes_session_once():
    init_route = respx.get(f"{BASE_URL}/initSession").mock(
        return_value=Response(200, json={"session_token": "sess-123"})
    )
    respx.post(f"{BASE_URL}/Ticket").mock(return_value=Response(201, json={"id": 42}))

    client = GLPIClient(BASE_URL, "app-tok", "user-tok")
    result = await client.create_ticket("Printer down", "HP printer on 3rd floor not responding")

    assert result["id"] == 42
    assert init_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_session_reused_across_calls():
    respx.get(f"{BASE_URL}/initSession").mock(return_value=Response(200, json={"session_token": "sess-abc"}))
    respx.post(f"{BASE_URL}/Ticket").mock(return_value=Response(201, json={"id": 1}))

    client = GLPIClient(BASE_URL, "app-tok", "user-tok")
    await client.create_ticket("Issue 1", "desc")
    await client.create_ticket("Issue 2", "desc")

    assert client._session_token == "sess-abc"


@pytest.mark.asyncio
@respx.mock
async def test_init_session_failure_raises():
    respx.get(f"{BASE_URL}/initSession").mock(return_value=Response(401, text="bad token"))
    client = GLPIClient(BASE_URL, "bad-app-tok", "bad-user-tok")

    with pytest.raises(GLPIAuthError):
        await client.create_ticket("x", "y")


@pytest.mark.asyncio
@respx.mock
async def test_list_open_tickets():
    respx.get(f"{BASE_URL}/initSession").mock(return_value=Response(200, json={"session_token": "s"}))
    respx.get(f"{BASE_URL}/Ticket").mock(return_value=Response(200, json=[{"id": 1, "status": 1}]))

    client = GLPIClient(BASE_URL, "app", "user")
    tickets = await client.list_open_tickets()

    assert tickets[0]["id"] == 1
