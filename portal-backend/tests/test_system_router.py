"""Tests for the system observability router (audit + health log readers,
findings 2.1/2.2 — these readers existed but were never exposed)."""
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.auth import create_access_token


def _headers():
    token = create_access_token("tester", ["viewer"])
    return {"Authorization": f"Bearer {token}"}


def test_audit_endpoint_returns_entries():
    client = TestClient(app)
    resp = client.get("/system/audit", headers=_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_health_endpoint_returns_entries():
    client = TestClient(app)
    resp = client.get("/system/health", headers=_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_system_endpoints_require_auth():
    client = TestClient(app)
    assert client.get("/system/audit").status_code in (401, 403)
    assert client.get("/system/health").status_code in (401, 403)