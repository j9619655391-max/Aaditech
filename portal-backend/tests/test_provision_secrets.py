"""Tests for app/provision_secrets.py — the single source of truth that backs
the "nothing secret before setup, everything generated on wizard submit"
behaviour (session 11)."""
from app import provision_secrets


def test_secret_keys_cover_every_platform():
    for key in ["WAZUH_API_PASSWORD", "ZABBIX_DB_PASSWORD", "ZABBIX_API_TOKEN",
                "GLPI_APP_TOKEN", "GLPI_USER_TOKEN", "OCS_DB_ROOT_PASSWORD",
                "MESHCENTRAL_API_KEY", "GRAFANA_ADMIN_PASSWORD",
                "GRAFANA_SERVICE_TOKEN", "JWT_SECRET", "WAZUH_ENROLL_KEY"]:
        assert key in provision_secrets.SECRET_KEYS


def test_generate_all_secrets_are_non_blank_and_unique():
    first = provision_secrets.generate_all_secrets()
    second = provision_secrets.generate_all_secrets()
    assert set(first) == set(provision_secrets.SECRET_KEYS)
    assert all(v for v in first.values())
    assert first != second  # fresh random set each call


def test_blank_env_has_all_keys_empty():
    text = provision_secrets.blank_env()
    for key in provision_secrets.SECRET_KEYS + provision_secrets.NON_SECRET_KEYS:
        line = [l for l in text.splitlines() if l.startswith(key + "=")]
        assert line, f"missing key {key}"
        value = line[0].split("=", 1)[1]
        # Every secret is blank before setup; only SMTP_PORT has a safe default.
        if key == "SMTP_PORT":
            assert value == "587"
        else:
            assert value == "", f"{key} should be blank before setup"
