"""
Tests for local username/password login (app/routers/auth_local.py) — the
bootstrap admin account path created by the setup wizard.
"""
import pytest
from fastapi.testclient import TestClient

from app import users
from app.main import app
from app.auth import decode_access_token

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_db():
    users.init_db("")
    yield


def _admin():
    users.create_user("admin", "password-123", ["viewer", "cleanup_approver"])


def test_local_login_returns_jwt():
    _admin()
    resp = client.post("/auth/login", json={"username": "admin", "password": "password-123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    payload = decode_access_token(body["access_token"])
    assert payload["sub"] == "admin"
    assert "cleanup_approver" in payload["roles"]


def test_local_login_rejects_bad_credentials():
    _admin()
    assert client.post("/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401
    assert client.post("/auth/login", json={"username": "ghost", "password": "whatever"}).status_code == 401


def test_local_login_requires_body():
    _admin()
    assert client.post("/auth/login", json={}).status_code == 401
