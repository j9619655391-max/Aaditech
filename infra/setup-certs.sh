#!/usr/bin/env bash
# ============================================================================
# setup-certs.sh
# Zero-touch HTTPS certificate automation (spec v1.4, §7.6).
#
# Runs BEFORE `docker compose up`. Performs:
#   1. One-time mkcert install (if not already present) + local CA creation
#      (mkcert -install) — the ONLY manual/interactive step in the whole
#      deployment, and this script does it automatically.
#   2. Issues a certificate for every web-facing service's hostname/localhost
#      alias, writing cert+key pairs into infra/certs/ (mounted into the
#      `certs` Docker volume via the compose file).
#
# Re-running is safe/idempotent — existing certs are reused unless --force.
# ============================================================================
set -euo pipefail

CERT_DIR="$(dirname "$0")/certs"
FORCE="${1:-}"

# Every web-facing service per the §7.6 port table. Container-internal
# hostnames are used since Nginx/each tool serves TLS from inside its
# own container on the aaditech-internal network.
SERVICES=(
  "portal:portal.aaditech.local,localhost"
  "wazuh-dashboard:wazuh-dashboard,localhost"
  "zabbix:zabbix-web,localhost"
  "glpi:glpi,localhost"
  "ocs:ocs-inventory,localhost"
  "grafana:grafana,localhost"
)

echo "== Aaditech Platform — HTTPS Certificate Setup (v1.4, mkcert) =="

if ! command -v mkcert &>/dev/null; then
  echo "[1/3] mkcert not found — installing..."
  if [[ "$(uname)" == "Linux" ]]; then
    curl -fsSL -o /usr/local/bin/mkcert \
      "https://dl.filippo.io/mkcert/latest?for=linux/amd64"
    chmod +x /usr/local/bin/mkcert
  elif [[ "$(uname)" == "Darwin" ]]; then
    brew install mkcert
  else
    echo "Unsupported OS for automated mkcert install. Install manually: https://github.com/FiloSottile/mkcert"
    exit 1
  fi
else
  echo "[1/3] mkcert already installed."
fi

echo "[2/3] Ensuring local CA is installed (one-time, automatic)..."
if mkcert -install 2>/dev/null; then
  echo "      CA installed into the system trust store."
else
  # Non-root / locked-down host: `mkcert -install` needs to write to the
  # system trust store. mkcert still auto-creates its root CA inside CAROOT
  # on first use, which is all the containers need to serve TLS. Browser
  # trust can be added later on the operator's machine (see the note below).
  echo "      WARNING: could not install the CA into the system trust store"
  echo "      (requires root). Continuing — the portal will still serve TLS;"
  echo "      export CAROOT/\$(mkcert -CAROOT)/rootCA.pem and trust it manually"
  echo "      on client machines to avoid browser warnings."
fi

mkdir -p "$CERT_DIR"

echo "[3/3] Issuing certificates for all web-facing services..."
for entry in "${SERVICES[@]}"; do
  name="${entry%%:*}"
  hosts="${entry#*:}"
  cert_file="$CERT_DIR/${name}.pem"
  key_file="$CERT_DIR/${name}-key.pem"

  if [[ -f "$cert_file" && "$FORCE" != "--force" ]]; then
    echo "  - $name: certificate already exists, skipping (use --force to reissue)"
    continue
  fi

  IFS=',' read -ra host_array <<< "$hosts"
  mkcert -cert-file "$cert_file" -key-file "$key_file" "${host_array[@]}"
  echo "  - $name: issued for [$hosts]"
done

# Convenience aliases matching the filenames each container expects
cp "$CERT_DIR/portal.pem" "$CERT_DIR/portal.crt" 2>/dev/null || true
cp "$CERT_DIR/portal-key.pem" "$CERT_DIR/portal.key" 2>/dev/null || true
cp "$CERT_DIR/grafana.pem" "$CERT_DIR/grafana.pem" 2>/dev/null || true

echo ""
echo "Done. Certificates written to: $CERT_DIR"
echo ""
echo "To trust these on a team member's laptop (no browser warnings there too),"
echo "have them run on their own machine, against the SAME CA root exported below:"
echo "  1. Copy the CA root: $(mkcert -CAROOT)/rootCA.pem"
echo "  2. On their machine: mkcert -install (after placing the same rootCA.pem in their CAROOT)"
echo ""
echo "Next: cd infra && docker compose up -d"
