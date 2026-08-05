#!/usr/bin/env bash
# ============================================================================
# setup.sh — ONE COMMAND to bring up the entire Aaditech server stack on
# Ubuntu (or any Docker host). This is the only script you need to run here.
#
# Usage:
#   cd infra
#   ./setup.sh
#
# Runs, in order, stopping immediately if any step fails:
#   1. generate-secrets.sh   — creates .env with all service credentials
#   2. setup-certs.sh        — installs mkcert CA + issues HTTPS certs
#   3. docker compose up -d  — brings up every container
#   4. waits for the portal's /health endpoint to respond, then reports
#      the final status of every container
#
# Re-running is safe: existing secrets/certs are reused (not regenerated),
# only missing pieces are created. Pass --force to regenerate secrets AND
# certs from scratch (this WILL break an existing deployment's credentials
# — only use on a fresh install).
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

FORCE="${1:-}"
MAX_HEALTH_WAIT_SECONDS=120

echo "=========================================================="
echo " Aaditech Platform — one-command setup"
echo "=========================================================="

# --- 0. Preflight: fail fast with a clear message instead of halfway in ---
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

# --- 1. Secrets ---
echo ""
echo "[1/4] Generating secrets..."
if [[ -f ".env" && "$FORCE" != "--force" ]]; then
  echo "      .env already exists — reusing it (pass --force to regenerate)."
else
  ./generate-secrets.sh "$FORCE"
fi

# --- 2. Certificates ---
echo ""
echo "[2/4] Setting up HTTPS certificates (mkcert)..."
./setup-certs.sh "$FORCE"

# --- 3. Bring up the stack ---
echo ""
echo "[3/4] Starting all containers (docker compose up -d)..."
docker compose up -d

# --- 4. Wait for the portal to actually be healthy, not just "started" ---
echo ""
echo "[4/4] Waiting for the portal to become healthy..."
elapsed=0
# The reverse proxy owns `/` (frontend) and `/api/*` (backend, prefix stripped),
# so the backend's /health is reachable at https://localhost/api/health. -f makes
# curl treat any non-2xx (e.g. a 404 before the portal is up) as a failure, so we
# truly wait instead of falsely succeeding on the first response.
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

echo ""
echo "=========================================================="
echo " Done. Portal is up: https://localhost"
echo "=========================================================="
docker compose ps
echo ""
echo "If this is the first run on this machine, trust the mkcert CA in your"
echo "browser too — setup-certs.sh printed the one-line command for that above."
echo ""
echo "NOTE: OCS Inventory is running by default (spec §7.6 port 8081, confirmed"
echo "as intended in session 5 — see docs/DEPLOYMENT.md)."