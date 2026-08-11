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

from app import crypto, users
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
    # Values containing spaces/#/= are double-quoted so they can't corrupt .env.
    assert 'COMPANY_NAME="Acme Corp"' in env
    assert "PORTAL_IP=10.73.77.58" in env
    assert "ADMIN_USERNAME=boss" in env
    assert "SMTP_HOST=smtp.hostinger.com" in env
    assert "SMTP_PASSWORD=mailbox-pass" in env
    assert "WAZUH_API_USER=aaditech-portal-svc" in env  # H7 — wizard writes it
    # Existing secrets are preserved
    assert "JWT_SECRET=abc" in env

    agent_cfg = crypto.decrypt_json(
        (setup_env / "agent-config.json").read_text(),
        [l for l in env.splitlines() if l.startswith("AGENT_CONFIG_KEY=")][0].split("=", 1)[1],
    )
    assert agent_cfg["managerIp"] == "10.73.77.58"
    assert agent_cfg["zabbixServerIp"] == "10.73.77.58"
    assert agent_cfg["wazuhEnrollKey"] == "preseed-key"
    assert agent_cfg["meshCentralUrl"] == "https://10.73.77.58:4433"
    # Versions pinned to match the deployed servers (wazuh 4.9.0 / zabbix 6.4).
    assert agent_cfg["wazuhAgentVersion"] == "4.9.0"
    assert agent_cfg["zabbixAgentVersion"] == "6.4.20"
    assert agent_cfg["meshId"] == ""

    assert (setup_env / ".provisioned").exists()

    admin = users.verify_credentials("boss", "strong-pass-123")
    assert admin is not None
    assert "cleanup_approver" in admin["roles"] and "viewer" in admin["roles"]


def test_provision_only_runs_once(setup_env):
    assert client.post("/api/setup/provision", json=VALID_PAYLOAD).status_code == 200
    resp = client.post("/api/setup/provision", json=VALID_PAYLOAD)
    assert resp.status_code == 409
    assert resp.json()["configured"] is True


def test_provision_collects_mesh_id(setup_env):
    """The optional MeshCentral device-group ID is persisted to .env AND
    written into the encrypted agent-config.json (H3 fix)."""
    payload = {**VALID_PAYLOAD, "mesh_id": "grp-42"}
    resp = client.post("/api/setup/provision", json=payload)
    assert resp.status_code == 200

    env = (setup_env / ".env").read_text()
    assert "MESHCENTRAL_MESH_ID=grp-42" in env

    agent_cfg = crypto.decrypt_json(
        (setup_env / "agent-config.json").read_text(),
        [l for l in env.splitlines() if l.startswith("AGENT_CONFIG_KEY=")][0].split("=", 1)[1],
    )
    assert agent_cfg["meshId"] == "grp-42"


def test_provision_preserves_existing_mesh_id(setup_env):
    """A mesh ID already present in infra/.env survives the wizard even when
    the payload omits it."""
    (setup_env / ".env").write_text(
        (setup_env / ".env").read_text() + "MESHCENTRAL_MESH_ID=grp-7\n"
    )
    resp = client.post("/api/setup/provision", json=VALID_PAYLOAD)
    assert resp.status_code == 200
    env = (setup_env / ".env").read_text()
    assert "MESHCENTRAL_MESH_ID=grp-7" in env


def test_env_values_with_special_chars_are_quoted(setup_env):
    """5.7 fix — a password/webhook containing '#', '=' or whitespace must not
    corrupt infra/.env and must round-trip through _load_env un-altered."""
    payload = {**VALID_PAYLOAD, "teams": {"webhook_url": "https://x.com?id=1#frag"}}
    resp = client.post("/api/setup/provision", json=payload)
    assert resp.status_code == 200

    env_text = (setup_env / ".env").read_text()
    assert 'TEAMS_WEBHOOK_URL="https://x.com?id=1#frag"' in env_text

    reloaded = next(
        l for l in env_text.splitlines() if l.startswith("TEAMS_WEBHOOK_URL=")
    ).split("=", 1)[1].strip()
    assert reloaded == '"https://x.com?id=1#frag"'


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


def test_telegram_requires_both_fields(setup_env):
    payload = {**VALID_PAYLOAD, "telegram": {"bot_token": "123:token", "chat_id": ""}}
    resp = client.post("/api/setup/provision", json=payload)
    assert resp.status_code == 400
    assert "BOTH" in resp.json()["detail"]


def test_teams_webhook_must_be_https(setup_env):
    payload = {**VALID_PAYLOAD, "teams": {"webhook_url": "http://insecure.example.com"}}
    resp = client.post("/api/setup/provision", json=payload)
    assert resp.status_code == 400
    assert "https" in resp.json()["detail"]


def test_provision_generates_every_service_secret_when_blank(setup_env):
    # .env has only JWT_SECRET + enroll key (see fixture) — every other
    # platform secret must be generated by the wizard.
    resp = client.post(
        "/api/setup/provision",
        json={
            **VALID_PAYLOAD,
            "telegram": {"bot_token": "123:abc", "chat_id": "-1001"},
            "teams": {"webhook_url": "https://outlook.office.com/webhook/x"},
            "github_pat": "github_pat_fake",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["telegram_channel"] is True
    assert body["teams_channel"] is True
    assert body["secrets_generated"] >= 15  # all SECRET_KEYS were blank

    env = (setup_env / ".env").read_text()
    # Platform secrets present and non-blank
    for key in ["WAZUH_API_PASSWORD", "ZABBIX_API_TOKEN", "GLPI_APP_TOKEN",
                "OCS_DB_ROOT_PASSWORD", "MESHCENTRAL_API_KEY",
                "GRAFANA_SERVICE_TOKEN", "JWT_SECRET"]:
        line = [l for l in env.splitlines() if l.startswith(key + "=")]
        assert line and line[0].split("=", 1)[1] != ""
    # Channels + GitHub written
    assert "TELEGRAM_BOT_TOKEN=123:abc" in env
    assert "TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/x" in env
    assert "GITHUB_BUILD_PAT=github_pat_fake" in env
    # Existing secrets preserved
    assert "JWT_SECRET=abc" in env


def test_status_reports_dependencies_from_preflight(setup_env):
    (setup_env / ".preflight.json").write_text(
        json.dumps({"date": "now", "total": 1, "critical_fail": False,
                    "items": [{"name": "docker", "status": "pass", "message": "installed"}]})
    )
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    deps = resp.json()["dependencies"]
    assert deps["items"][0]["name"] == "docker"
    assert deps["items"][0]["status"] == "pass"
