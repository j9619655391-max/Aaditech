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

    # Deployment identity (set by the one-click setup wizard)
    company_name: str = ""
    portal_ip: str = ""
    wazuh_enroll_key: str = ""

    # Email notification channel (SMTP) — auto-filled by the setup wizard from
    # the chosen provider preset (gmail/hotmail/office365/hostinger).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = ""
    smtp_use_tls: str = "starttls"   # "starttls" | "ssl" | "none"

    # Alerting backbone (§3.6) — Telegram/Slack/MS Teams primary, empty string
    # disables a channel. All three can be configured from the setup wizard.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    slack_webhook_url: str = ""
    teams_webhook_url: str = ""

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

    # Agent build via GitHub Actions (optional) — POST /api/agent-installer/build
    # triggers build-agent-installer.yml and pulls the .exe into installer_dir.
    # PAT needs `actions: read+write` on the repo. Blank => endpoint reports
    # "not configured" and the .exe must be built manually.
    github_build_pat: str = ""
    github_repo: str = "j9619655391-max/Aaditech"

    # One-click setup (bootstrap) mode — set only on the temporary `setup`
    # service. When true, the backend serves the setup wizard instead of the
    # normal portal, and can write infra/.env via the mounted host directory.
    setup_mode: bool = Field(default=False, validation_alias="SETUP_MODE")
    infra_dir: str = Field(default="", validation_alias="INFRA_DIR")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
