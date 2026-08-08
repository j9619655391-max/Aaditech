"""
Tests for the one-click setup wizard (app/routers/setup.py):
  - status reports not-configured before provisioning
  - provision generates .env additions, agent-config.json, the admin account
    and the .provisioned marker
  - SMTP provider presets are applied (only username/password needed)
  - invalid input is rejected
"""
import json

import pytest
from fastapi.testclient import TestClient

from app import users
from app.main import app

client = TestClient(app)

VALID_PAYLOAD = {
    "company_name": "Acme Corp",
    "admin_username": "boss",
    "admin_password": "strong-pass-123",
    "local_ip": "10.73.77.58",
    "email": {
        "provider": "hostinger",
        "address": "alerts@acme.com",
        "username": "alerts@acme.com",
        "password": "mailbox-pass",
    },
}


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    """Point the wizard at a temp infra dir and switch on SETUP_MODE."""
    (tmp_path / ".env").write_text("JWT_SECRET=abc\nWAZUH_ENROLL_KEY=preseed-key\n")
    monkeypatch.setattr("app.routers.setup.settings.setup_mode", True)
    monkeypatch.setattr("app.routers.setup.settings.infra_dir", str(tmp_path))
    users.init_db("")  # fresh in-memory user store
    return tmp_path


def test_status_reports_unconfigured_before_provision(setup_env):
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["company_name"] == ""


def test_provision_generates_config_and_admin(setup_env):
    resp = client.post("/api/setup/provision", json=VALID_PAYLOAD)
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["admin_username"] == "boss"
    assert body["portal_url"] == "https://10.73.77.58"
    assert body["enrollment_key"] == "preseed-key"  # preserved, not regenerated
    assert body["smtp"] == {"host": "smtp.hostinger.com", "port": 465, "tls": "ssl"}

    env = (setup_env / ".env").read_text()
    assert "COMPANY_NAME=Acme Corp" in env
    assert "PORTAL_IP=10.73.77.58" in env
    assert "ADMIN_USERNAME=boss" in env
    assert "SMTP_HOST=smtp.hostinger.com" in env
    assert "SMTP_PASSWORD=mailbox-pass" in env
    # Existing secrets are preserved
    assert "JWT_SECRET=abc" in env

    agent_cfg = json.loads((setup_env / "agent-config.json").read_text())
    assert agent_cfg["managerIp"] == "10.73.77.58"
    assert agent_cfg["zabbixServerIp"] == "10.73.77.58"
    assert agent_cfg["wazuhEnrollKey"] == "preseed-key"
    assert agent_cfg["meshCentralUrl"] == "https://10.73.77.58:4433"

    assert (setup_env / ".provisioned").exists()

    admin = users.verify_credentials("boss", "strong-pass-123")
    assert admin is not None
    assert "cleanup_approver" in admin["roles"] and "viewer" in admin["roles"]


def test_provision_only_runs_once(setup_env):
    assert client.post("/api/setup/provision", json=VALID_PAYLOAD).status_code == 200
    resp = client.post("/api/setup/provision", json=VALID_PAYLOAD)
    assert resp.status_code == 409
    assert resp.json()["configured"] is True


def test_provision_rejects_bad_ip(setup_env):
    payload = {**VALID_PAYLOAD, "local_ip": "not-an-ip"}
    resp = client.post("/api/setup/provision", json=payload)
    assert resp.status_code == 400


def test_provision_rejects_short_password(setup_env):
    payload = {**VALID_PAYLOAD, "admin_password": "short"}
    resp = client.post("/api/setup/provision", json=payload)
    assert resp.status_code == 400


def test_provision_rejects_unknown_provider(setup_env):
    payload = {**VALID_PAYLOAD, "email": {**VALID_PAYLOAD["email"], "provider": "aol"}}
    resp = client.post("/api/setup/provision", json=payload)
    assert resp.status_code == 400


def test_status_returns_configured_in_normal_mode(monkeypatch):
    monkeypatch.setattr("app.routers.setup.settings.setup_mode", False)
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    assert resp.json()["configured"] is True


@pytest.mark.parametrize(
    "provider,expected",
    [
        ("gmail", {"host": "smtp.gmail.com", "port": 465, "tls": "ssl"}),
        ("office365", {"host": "smtp.office365.com", "port": 587, "tls": "starttls"}),
        ("hotmail", {"host": "smtp-mail.outlook.com", "port": 587, "tls": "starttls"}),
    ],
)
def test_provider_presets_are_applied(setup_env, provider, expected):
    payload = {**VALID_PAYLOAD, "email": {**VALID_PAYLOAD["email"], "provider": provider}}
    resp = client.post("/api/setup/provision", json=payload)
    assert resp.status_code == 200
    assert resp.json()["smtp"] == expected
