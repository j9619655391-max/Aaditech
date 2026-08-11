"""Unit tests for MeshCentralClient. Run with: pytest tests/test_meshcentral_client.py"""
import pytest
import respx
from httpx import Response

from app.integrations.meshcentral_client import MeshCentralClient, MeshCentralError

BASE_URL = "https://meshcentral:443"
API_PREFIX = "/meshcentral/api"


@pytest.mark.asyncio
@respx.mock
async def test_start_remote_session_success():
    respx.post(f"{BASE_URL}{API_PREFIX}/remote/session").mock(
        return_value=Response(200, json={"sessionId": "sess-1", "token": "abc123"})
    )
    client = MeshCentralClient(BASE_URL, "key", public_url="https://portal.aaditech.local")
    result = await client.start_remote_session("device-1", "jdoe")

    assert result["session_id"] == "sess-1"
    # Embeddable URL must be browser-reachable (public host), never the
    # internal container name.
    assert "meshcentral:443" not in result["session_url"]
    assert result["session_url"].startswith("https://portal.aaditech.local/meshcentral/")
    assert "token=abc123" in result["session_url"]


@pytest.mark.asyncio
@respx.mock
async def test_start_remote_session_uses_public_url_when_set():
    respx.post(f"{BASE_URL}{API_PREFIX}/remote/session").mock(
        return_value=Response(200, json={"sessionId": "sess-2", "token": "tok"})
    )
    client = MeshCentralClient(BASE_URL, "key", public_url="https://portal.example.com")
    result = await client.start_remote_session("device-2", "jdoe")

    assert result["session_url"].startswith("https://portal.example.com/meshcentral/")


@pytest.mark.asyncio
@respx.mock
async def test_start_remote_session_failure_raises():
    respx.post(f"{BASE_URL}{API_PREFIX}/remote/session").mock(return_value=Response(403, text="device offline"))
    client = MeshCentralClient(BASE_URL, "key")

    with pytest.raises(MeshCentralError):
        await client.start_remote_session("device-2", "jdoe")


@pytest.mark.asyncio
@respx.mock
async def test_end_session():
    route = respx.delete(f"{BASE_URL}{API_PREFIX}/remote/session/sess-1").mock(return_value=Response(204))
    client = MeshCentralClient(BASE_URL, "key")
    await client.end_session("sess-1")

    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_list_devices():
    respx.get(f"{BASE_URL}{API_PREFIX}/server/devices").mock(
        return_value=Response(200, json=[{"_id": "node-1", "name": "PC1"}])
    )
    client = MeshCentralClient(BASE_URL, "key")
    devices = await client.list_devices()

    assert devices[0]["_id"] == "node-1"
