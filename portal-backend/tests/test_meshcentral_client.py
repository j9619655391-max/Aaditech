"""Unit tests for MeshCentralClient. Run with: pytest tests/test_meshcentral_client.py"""
import pytest
import respx
from httpx import Response

from app.integrations.meshcentral_client import MeshCentralClient, MeshCentralError

BASE_URL = "https://meshcentral:443"


@pytest.mark.asyncio
@respx.mock
async def test_start_remote_session_success():
    respx.post(f"{BASE_URL}/api/sessions").mock(
        return_value=Response(200, json={"sessionId": "sess-1", "sessionUrl": "wss://internal/proxy"})
    )
    client = MeshCentralClient(BASE_URL, "key")
    result = await client.start_remote_session("device-1", "jdoe")

    assert result["sessionId"] == "sess-1"


@pytest.mark.asyncio
@respx.mock
async def test_start_remote_session_failure_raises():
    respx.post(f"{BASE_URL}/api/sessions").mock(return_value=Response(403, text="device offline"))
    client = MeshCentralClient(BASE_URL, "key")

    with pytest.raises(MeshCentralError):
        await client.start_remote_session("device-2", "jdoe")


@pytest.mark.asyncio
@respx.mock
async def test_end_session():
    route = respx.delete(f"{BASE_URL}/api/sessions/sess-1").mock(return_value=Response(204))
    client = MeshCentralClient(BASE_URL, "key")
    await client.end_session("sess-1")

    assert route.called
