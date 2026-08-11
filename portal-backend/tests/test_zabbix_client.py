"""Unit tests for ZabbixClient. Run with: pytest tests/test_zabbix_client.py"""
import pytest
import respx
from httpx import Response

from app.integrations.zabbix_client import ZabbixAPIError, ZabbixClient

BASE_URL = "http://zabbix-web:8080/api_jsonrpc.php"


@pytest.mark.asyncio
@respx.mock
async def test_get_host_status():
    respx.post(BASE_URL).mock(
        return_value=Response(
            200,
            json={"jsonrpc": "2.0", "result": [{"hostid": "1", "host": "srv01", "status": "0"}], "id": 1},
        )
    )
    client = ZabbixClient(BASE_URL, "tok")
    hosts = await client.get_host_status()

    assert hosts[0]["host"] == "srv01"


@pytest.mark.asyncio
@respx.mock
async def test_api_error_raises():
    respx.post(BASE_URL).mock(
        return_value=Response(
            200,
            json={"jsonrpc": "2.0", "error": {"code": -32602, "message": "Invalid params"}, "id": 1},
        )
    )
    client = ZabbixClient(BASE_URL, "tok")

    with pytest.raises(ZabbixAPIError):
        await client.get_host_status()


@pytest.mark.asyncio
@respx.mock
async def test_active_triggers_severity_param():
    route = respx.post(BASE_URL).mock(
        return_value=Response(200, json={"jsonrpc": "2.0", "result": [], "id": 1})
    )
    client = ZabbixClient(BASE_URL, "tok")
    await client.get_active_triggers(min_severity=4)

    sent_body = route.calls.last.request.content
    assert b'"min_severity": 4' in sent_body


@pytest.mark.asyncio
@respx.mock
async def test_active_problems_uses_problem_get():
    route = respx.post(BASE_URL).mock(
        return_value=Response(200, json={"jsonrpc": "2.0", "result": [], "id": 1})
    )
    client = ZabbixClient(BASE_URL, "tok")
    await client.get_active_problems(min_severity=3)

    sent_body = route.calls.last.request.content
    assert b'"problem.get"' in sent_body
    assert b'"min_severity": 3' in sent_body
    assert b'"recent"' in sent_body


@pytest.mark.asyncio
@respx.mock
async def test_request_id_increments():
    respx.post(BASE_URL).mock(return_value=Response(200, json={"jsonrpc": "2.0", "result": [], "id": 1}))
    client = ZabbixClient(BASE_URL, "tok")

    await client.get_host_status()
    await client.get_host_status()

    assert client._request_id == 2
