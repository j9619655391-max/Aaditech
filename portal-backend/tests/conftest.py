"""
Shared pytest fixtures. Sets dummy environment variables BEFORE any
`app.*` module is imported, since app.config.Settings() requires these
at import time. This lets the full test suite run without any real
secrets or a real infra/.env file.
"""
import os

os.environ.setdefault("WAZUH_API_USER", "test-user")
os.environ.setdefault("WAZUH_API_PASSWORD", "test-pass")
os.environ.setdefault("ZABBIX_API_TOKEN", "test-token")
os.environ.setdefault("GLPI_APP_TOKEN", "test-app-token")
os.environ.setdefault("GLPI_USER_TOKEN", "test-user-token")
os.environ.setdefault("MESHCENTRAL_API_KEY", "test-mesh-key")
os.environ.setdefault("GRAFANA_SERVICE_TOKEN", "test-grafana-token")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-unit-tests-only")
