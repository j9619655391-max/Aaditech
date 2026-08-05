"""
Unit tests for WazuhClient. Uses `respx` to mock HTTP responses — no live
Wazuh manager is required to run these. Run with: pytest tests/test_wazuh_client.py
"""
import pytest
import respx
from httpx import Response

from app.integrations.wazuh_client import WazuhAuthError, WazuhClient

BASE_URL = "https://wazuh-manager:55000"


@pytest.mark.asyncio
@respx.mock
async def test_authenticate_success():
    respx.post(f"{BASE_URL}/security/user/authenticate").mock(
        return_value=Response(200, json={"data": {"token": "fake-jwt-token"}})
    )
    respx.get(f"{BASE_URL}/alerts").mock(
        return_value=Response(200, json={"data": {"affected_items": [{"rule": {"level": 10}}]}})
    )

    client = WazuhClient(BASE_URL, "svc", "pass")
    alerts = await client.get_alerts(limit=10)

    assert len(alerts) == 1
    assert client._token == "fake-jwt-token"


@pytest.mark.asyncio
@respx.mock
async def test_authenticate_failure_raises():
    respx.post(f"{BASE_URL}/security/user/authenticate").mock(
        return_value=Response(401, text="unauthorized")
    )
    client = WazuhClient(BASE_URL, "svc", "wrongpass")

    with pytest.raises(WazuhAuthError):
        await client.get_alerts()


@pytest.mark.asyncio
@respx.mock
async def test_get_alerts_filters_by_min_level():
    respx.post(f"{BASE_URL}/security/user/authenticate").mock(
        return_value=Response(200, json={"data": {"token": "tok"}})
    )
    respx.get(f"{BASE_URL}/alerts").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "affected_items": [
                        {"rule": {"level": 3}},
                        {"rule": {"level": 12}},
                    ]
                }
            },
        )
    )
    client = WazuhClient(BASE_URL, "svc", "pass")
    alerts = await client.get_alerts(level_min=10)

    assert len(alerts) == 1
    assert alerts[0]["rule"]["level"] == 12


@pytest.mark.asyncio
@respx.mock
async def test_token_refresh_on_401():
    auth_route = respx.post(f"{BASE_URL}/security/user/authenticate").mock(
        return_value=Response(200, json={"data": {"token": "tok1"}})
    )
    alerts_route = respx.get(f"{BASE_URL}/alerts")
    alerts_route.side_effect = [
        Response(401, text="expired"),
        Response(200, json={"data": {"affected_items": []}}),
    ]

    client = WazuhClient(BASE_URL, "svc", "pass")
    result = await client.get_alerts()

    assert result == []
    assert auth_route.call_count == 2  # re-authenticated after 401
