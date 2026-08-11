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


def test_rate_limiter_locks_after_max_failures():
    _admin()
    from app.routers.auth_local import MAX_FAILED_ATTEMPTS, _failures, _is_locked

    _failures.clear()
    for _ in range(MAX_FAILED_ATTEMPTS):
        assert (
            client.post(
                "/auth/login",
                json={"username": "admin", "password": "wrong"},
            ).status_code
            == 401
        )
    # The next attempt — even with the CORRECT password — is refused (429).
    assert (
        client.post(
            "/auth/login",
            json={"username": "admin", "password": "password-123"},
        ).status_code
        == 429
    )
    assert _is_locked("admin|testclient")
    _failures.clear()


def test_successful_login_clears_failure_history():
    _admin()
    from app.routers.auth_local import _failures

    _failures.clear()
    client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert _failures
    resp = client.post("/auth/login", json={"username": "admin", "password": "password-123"})
    assert resp.status_code == 200
    assert not _failures


def test_verify_id_token_rejects_forged_token():
    """Finding 3.3: a forged/unsigned id_token must never be accepted. With
    Azure envs absent in unit tests, `verify_id_token` refuses up front
    (unconfigured); with a configured tenant it still rejects the signature."""

    from app import ms_oauth

    with pytest.raises((ValueError, RuntimeError)):
        ms_oauth.verify_id_token("not.a.jwt")
