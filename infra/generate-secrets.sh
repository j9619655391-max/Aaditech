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

# Alerting backbone (§3.6) — Telegram/Slack are PRIMARY and must be filled in
# manually (bot token / webhook come from your own Telegram bot & Slack app —
# these cannot be auto-generated). Leave blank to disable a channel.
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SLACK_WEBHOOK_URL=

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
