#!/usr/bin/env bash
# ============================================================================
# generate-secrets.sh
# Auto-generates strong random secrets for every backend service and writes
# them to infra/.env. Run this ONCE before `docker compose up`.
# Re-running will NOT overwrite an existing .env unless --force is passed,
# to avoid breaking already-provisioned services.
# ============================================================================
set -euo pipefail

ENV_FILE="$(dirname "$0")/.env"
FORCE="${1:-}"

if [[ -f "$ENV_FILE" && "$FORCE" != "--force" ]]; then
  echo "infra/.env already exists. Use --force to regenerate (this will break existing deployments)."
  exit 1
fi

rand() {
  # 32-byte URL-safe random secret
  openssl rand -base64 32 | tr -d '\n' | tr '+/' '-_'
}

cat > "$ENV_FILE" <<EOF
# Auto-generated $(date -u +%Y-%m-%dT%H:%M:%SZ) — do not commit this file to version control.

# Wazuh
WAZUH_API_USER=aaditech-portal-svc
WAZUH_API_PASSWORD=$(rand)

# Zabbix
ZABBIX_DB_PASSWORD=$(rand)
ZABBIX_API_TOKEN=$(rand)

# GLPI
GLPI_DB_ROOT_PASSWORD=$(rand)
GLPI_DB_PASSWORD=$(rand)
GLPI_APP_TOKEN=$(rand)
GLPI_USER_TOKEN=$(rand)

# OCS Inventory (flagged inconsistency — see docker-compose.yml comment; §7.6 lists a host
# port for this service but §2's main stack table does not include it — confirm intent)
OCS_DB_ROOT_PASSWORD=$(rand)
OCS_DB_PASSWORD=$(rand)

# MeshCentral
MESHCENTRAL_API_KEY=$(rand)

# Grafana
GRAFANA_ADMIN_PASSWORD=$(rand)
GRAFANA_SERVICE_TOKEN=$(rand)

# Portal
JWT_SECRET=$(rand)

# One-click setup (filled by the setup wizard; only the random enrollment key
# is pre-generated here so every deploy has a unique agent enroll key):
WAZUH_ENROLL_KEY=$(rand)

# Agent config at-rest encryption key (Fernet key seed) — written encrypted
# by the wizard to infra/agent-config.json (app/crypto.py).
AGENT_CONFIG_KEY=$(rand)

COMPANY_NAME=
PORTAL_IP=

# Email notification channel (SMTP) — auto-filled from the wizard's provider
# preset. Blank => email notifications disabled.
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_ADDRESS=
SMTP_USE_TLS=starttls

# Alerting backbone (§3.6) — Telegram/Slack/MS Teams are PRIMARY and are filled
# in either manually or via the one-click setup wizard (bot token / webhook
# come from your own Telegram bot, Slack app & Teams connector — these cannot
# be auto-generated). Leave blank to disable a channel.
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SLACK_WEBHOOK_URL=
TEAMS_WEBHOOK_URL=

# Agent build via GitHub Actions (optional) — lets the portal trigger a
# build-agent-installer.yml run and pull Aaditech-Agent-Setup.exe. Blank =>
# build the .exe manually (build-agent-installer.ps1 on Windows, or
# infra/fetch-agent-build.sh with a PAT supplied on the command line).
GITHUB_BUILD_PAT=
GITHUB_REPO=j9619655391-max/Aaditech

# Office 365 / Azure AD (§7.5) — secondary/reporting channel only, and SSO login.
# Fill in after completing the Phase 0 Azure app registration spike (§6).
# AZURE_ADMIN_GROUP_IDS: comma-separated Azure AD group object IDs whose members
# become CLEANUP_APPROVER at login (§7.1); empty => everyone is Viewer+Engineer.
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
AZURE_TENANT_ID=
AZURE_ADMIN_GROUP_IDS=

# Category B quarantine (§3.5) — network share path for off-volume quarantine
# storage (v1.2 default). Leave blank to fall back to a local second-volume
# path if present, or the 24h emergency-hold-only mode on single-disk endpoints.
QUARANTINE_NETWORK_SHARE=
EOF

chmod 600 "$ENV_FILE"
echo "Secrets generated at $ENV_FILE (permissions set to 600)."
echo "Next: cd infra && docker compose up -d"
