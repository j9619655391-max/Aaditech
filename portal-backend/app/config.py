"""
Central configuration for the Aaditech Portal backend.
All values are loaded from environment variables (populated via
infra/.env → docker-compose.yml). Nothing is hardcoded.
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Wazuh
    wazuh_api_url: str = "https://wazuh-manager:55000"
    wazuh_api_user: str
    wazuh_api_password: str

    # Zabbix
    zabbix_api_url: str = "http://zabbix-web:8080/api_jsonrpc.php"
    zabbix_api_token: str

    # GLPI
    glpi_api_url: str = "http://glpi:80/apirest.php"
    glpi_app_token: str
    glpi_user_token: str

    # MeshCentral
    meshcentral_api_url: str = "https://meshcentral:443"
    meshcentral_api_key: str

    # Grafana
    grafana_url: str = "http://grafana:3000"
    grafana_service_token: str

    # Portal
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 480
    portal_env: str = "development"

    # Alerting backbone (§3.6) — Telegram/Slack primary, empty string disables a channel
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    slack_webhook_url: str = ""

    # Office 365 / Azure AD (§7.5) — secondary/reporting channel + SSO only
    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_tenant_id: str = ""
    # Comma-separated Azure AD group object IDs whose members become
    # CLEANUP_APPROVER at login (§7.1). Empty => everyone is Viewer+Engineer.
    azure_admin_group_ids: str = ""

    # Category B quarantine policy (§3.5, v1.2 refinement)
    quarantine_standard_hold_days: int = 7
    quarantine_emergency_hold_hours: int = 24
    quarantine_network_share: str = ""

    # Persistent storage (SQLite file path). Empty => in-memory (dev/tests only).
    # Bound explicitly to AADITECH_DB_PATH (matches docker-compose.yml and the
    # *_store module env read); without this alias, pydantic-settings would look
    # for a `DB_PATH` env var and silently fall back to in-memory storage.
    db_path: str = Field(default="", validation_alias="AADITECH_DB_PATH")

    # Agent installer distribution (§7.2) — where the compiled
    # Aaditech-Agent-Setup.exe lives (env-mounted directory). Empty/default
    # => installer reports "not available" instead of a false download.
    installer_dir: str = Field(default="", validation_alias="AADITECH_INSTALLER_DIR")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
