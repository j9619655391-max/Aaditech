#!/usr/bin/env bash
# ============================================================================
# install.sh — ONE COMMAND to deploy the entire Aaditech platform on a fresh
# (or any) Docker host.
#
# Usage:
#   git pull
#   cd infra
#   ./install.sh
#
# What it does, in order (stopping immediately if any step fails):
#   1. Preflight — docker, docker compose, curl, openssl present.
#   2. Generates infra/.env with all service secrets (if missing) — random
#      tokens, DB passwords, and a unique Wazuh agent enrollment key.
#   3. Starts ONLY the temporary `setup` service (compose profile "bootstrap")
#      and opens/prints the SETUP WIZARD: http://localhost:8080/setup
#        * Company name
#        * Admin username + password
#        * Local server IP
#        * Notification email (provider auto-configured:
#          gmail / hotmail / office365 / hostinger — only username+password
#          needed)
#      Everything else — tokens, certificates, endpoints, agent enrollment
#      key, agent config — is generated automatically on submit.
#   4. Waits for the wizard to finish (polling /api/setup/status).
#   5. Stops the setup service and brings up the FULL stack (nginx + portal +
#      Wazuh + Zabbix + GLPI + OCS + MeshCentral + Grafana) with HTTPS certs.
#   6. Waits for the portal to be healthy and prints the final summary.
#
# Re-running is safe: existing .env secrets and certs are reused, and the
# wizard only appears again if .provisioned is absent.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

WIZARD_PORT=8080
MAX_SETUP_WAIT_SECONDS=900          # 15 min to fill the wizard
MAX_HEALTH_WAIT_SECONDS=180

echo "=========================================================="
echo " Aaditech Platform — one-click deployment"
echo "=========================================================="

# --- 1. Preflight -----------------------------------------------------------
for cmd in docker openssl curl; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: '$cmd' is required but not installed. Install it and re-run."
    exit 1
  fi
done
if ! docker compose version &>/dev/null; then
  echo "ERROR: 'docker compose' (v2) not found. Install the Docker Compose plugin and re-run."
  exit 1
fi

# --- 2. Secrets ---------------------------------------------------------------
echo ""
if [[ -f ".env" ]]; then
  echo "[1/6] infra/.env already exists — reusing existing secrets."
else
  echo "[1/6] Generating all service secrets and the agent enrollment key..."
  ./generate-secrets.sh
fi

# --- 3. Bootstrap setup wizard -------------------------------------------------
echo ""
echo "[2/6] Starting the setup wizard (this is the ONLY service up for now)..."
docker compose --profile bootstrap up -d setup

# --- 4. Wait for the wizard API -------------------------------------------------
echo ""
echo "      Waiting for the wizard to come up..."
elapsed=0
until curl -fs --max-time 3 http://localhost:${WIZARD_PORT}/api/setup/status &>/dev/null; do
  if (( elapsed >= 60 )); then
    echo "ERROR: setup wizard did not come up. Check: docker compose ps"
    exit 1
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done

if [[ -f ".provisioned" ]]; then
  echo "      Already provisioned (found .provisioned) — skipping the wizard."
else
  echo ""
  echo "=========================================================="
  echo "  SETUP WIZARD:  http://localhost:${WIZARD_PORT}/setup"
  echo ""
  echo "  Fill in (everything else is generated for you):"
  echo "    • Company name"
  echo "    • Admin username + password"
  echo "    • Local server IP"
  echo "    • Notification email (provider auto-configured:"
  echo "      gmail / hotmail / office365 / hostinger — just username+password)"
  echo "=========================================================="
  echo ""
  echo "Waiting for you to finish the wizard (up to $((MAX_SETUP_WAIT_SECONDS / 60)) minutes)..."
  echo "(Ctrl+C aborts; re-running install.sh resumes the wizard.)"

  elapsed=0
  until curl -fs --max-time 3 http://localhost:${WIZARD_PORT}/api/setup/status \
        | grep -q '"configured": true'; do
    if (( elapsed >= MAX_SETUP_WAIT_SECONDS )); then
      echo ""
      echo "ERROR: timed out waiting for the setup wizard. Re-run ./install.sh to continue."
      exit 1
    fi
    sleep 5
    elapsed=$((elapsed + 5))
    if (( elapsed % 60 == 0 )); then
      echo "      ...still waiting (${elapsed}s elapsed) — finish the form at"
      echo "      http://localhost:${WIZARD_PORT}/setup"
    fi
  done
  echo ""
  echo "      Wizard complete — configuration generated."
fi

# --- 5. Full stack --------------------------------------------------------------
echo ""
echo "[3/6] Stopping the setup service..."
docker compose stop setup

echo "[4/6] Issuing HTTPS certificates (mkcert, includes your server IP)..."
./setup-certs.sh

echo "[5/6] Starting the FULL stack (portal + Wazuh + Zabbix + GLPI + OCS + MeshCentral + Grafana)..."
docker compose up -d

# --- 6. Health check ------------------------------------------------------------
echo ""
echo "[6/6] Waiting for the portal to become healthy..."
elapsed=0
until curl -kfs --max-time 3 https://localhost/api/health &>/dev/null; do
  if (( elapsed >= MAX_HEALTH_WAIT_SECONDS )); then
    echo ""
    echo "WARNING: Portal did not become healthy within ${MAX_HEALTH_WAIT_SECONDS}s."
    echo "Run 'docker compose ps' and 'docker compose logs portal-backend' to diagnose."
    exit 1
  fi
  sleep 5
  elapsed=$((elapsed + 5))
  echo "      ...still waiting (${elapsed}s elapsed)"
done

IP=$(grep -E '^PORTAL_IP=' .env 2>/dev/null | cut -d= -f2 || true)
COMPANY=$(grep -E '^COMPANY_NAME=' .env 2>/dev/null | cut -d= -f2 || true)
ADMIN=$(grep -E '^ADMIN_USERNAME=' .env 2>/dev/null | cut -d= -f2 || true)

echo ""
echo "=========================================================="
echo " Done — Aaditech Platform is UP."
echo "=========================================================="
[[ -n "$COMPANY" ]] && echo " Company:        $COMPANY"
echo " Portal URL:     https://${IP:-localhost}"
[[ -n "$ADMIN" ]] && echo " Admin login:    $ADMIN"
echo " Agent setup:    infra/agent-config.json (generated by the wizard)"
echo ""
echo " For a summary of every container:  docker compose ps"
echo "=========================================================="
docker compose ps
