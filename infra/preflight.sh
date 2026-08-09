#!/usr/bin/env bash
# ============================================================================
# preflight.sh — host dependency check for the one-click install
#
# Verifies everything ./install.sh needs BEFORE the setup wizard starts, so a
# broken host fails fast with a clear report instead of half-way through
# Docker pulls. Results are printed AND written to infra/.preflight.json so
# the setup wizard can render the same checklist.
#
# Exit code: 0 if no CRITICAL failure (warnings are allowed), else 1.
# Usage:   ./preflight.sh
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---- helpers ---------------------------------------------------------------
status=""           # "pass" | "fail" | "warn"
message=""
declare -a ITEMS=()  # JSON fragments

pass() { status="pass"; message=""; }
fail() { status="fail"; message="$1"; }
warn() { status="warn"; message="$1"; }

has_cmd() { command -v "$1" &>/dev/null; }

record() { # name  status  message
  ITEMS+=("{\"name\":\"$1\",\"status\":\"$2\",\"message\":\"$3\"}")
}

# ---- 1. required commands (CRITICAL — fail fast) ---------------------------
REQUIRED=(docker openssl curl python3)
for cmd in "${REQUIRED[@]}"; do
  if has_cmd "$cmd"; then
    printf '%-28s %s\n' "[$cmd]" "PASS"
    record "$cmd" "pass" "installed"
  else
    printf '%-28s %s\n' "[$cmd]" "FAIL — required, not installed"
    record "$cmd" "fail" "required, not installed"
  fi
done

# ---- 2. docker compose plugin (v2) ------------------------------------------
if docker compose version &>/dev/null; then
  printf '%-28s %s\n' "[docker compose v2]" "PASS"
  record "docker compose v2" "pass" "$(docker compose version --short 2>/dev/null)"
else
  printf '%-28s %s\n' "[docker compose v2]" "FAIL — Docker Compose plugin missing"
  record "docker compose v2" "fail" "install the Docker Compose v2 plugin"
fi

# ---- 3. mkcert (warn: setup-certs.sh auto-installs it) ----------------------
if has_cmd mkcert; then
  printf '%-28s %s\n' "[mkcert]" "PASS"
  record "mkcert" "pass" "installed"
else
  printf '%-28s %s\n' "[mkcert]" "WARN — will be auto-installed by setup-certs.sh (needs internet)"
  record "mkcert" "warn" "auto-installed later by setup-certs.sh"
fi

# ---- 4. host ports free (CRITICAL) ------------------------------------------
# Every host port the stack binds (spec §7.6 port table). A port already in
# use breaks that service — fail so the operator frees it first.
PORTS=(443 1514 1515 55000 5601 10051 8082 8080 8081 4433 3000)
occupied=""
for p in "${PORTS[@]}"; do
  if python3 - "$p" <<'PY' &>/dev/null; then
import socket, sys
s = socket.socket()
try:
    s.bind(("0.0.0.0", int(sys.argv[1])))
    s.close()
    sys.exit(0)   # free
except OSError:
    sys.exit(1)   # in use
PY
    :
  else
    occupied="$occupied $p"
  fi
done
if [[ -z "$occupied" ]]; then
  printf '%-28s %s\n' "[host ports]" "PASS — all ${#PORTS[@]} ports free"
  record "host ports" "pass" "all ${#PORTS[@]} stack ports free"
else
  printf '%-28s %s\n' "[host ports]" "FAIL — in use:$occupied"
  record "host ports" "fail" "ports in use:$occupied — free them first"
fi

# ---- 5. disk space (WARN: images + data need room) --------------------------
FREE_MB=$(df -Pk . | awk 'NR==2 {print $4}')
FREE_GB=$((FREE_MB / 1024))
if [[ "$FREE_GB" -ge 20 ]]; then
  printf '%-28s %s\n' "[disk space]" "PASS — ${FREE_GB} GB free"
  record "disk space" "pass" "${FREE_GB} GB free"
else
  printf '%-28s %s\n' "[disk space]" "WARN — only ${FREE_GB} GB free (recommend >= 20 GB)"
  record "disk space" "warn" "${FREE_GB} GB free, recommend >= 20 GB"
fi

# ---- 6. internet (WARN: needs to pull images / download mkcert) -------------
if curl -fs --max-time 8 https://docker.io &>/dev/null || curl -fs --max-time 8 https://registry-1.docker.io &>/dev/null; then
  printf '%-28s %s\n' "[internet]" "PASS"
  record "internet" "pass" "reachable"
else
  printf '%-28s %s\n' "[internet]" "WARN — no internet (docker pulls / mkcert download will fail)"
  record "internet" "warn" "no internet detected"
fi

# ---- summary ----------------------------------------------------------------
critical=0
for item in "${ITEMS[@]}"; do
  [[ "$item" == *'"status":"fail"'* ]] && critical=1
done

cat > .preflight.json <<JSON
{
  "date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "total": ${#ITEMS[@]},
  "critical_fail": $critical,
  "items": [ $(printf '%s,' "${ITEMS[@]}" | sed 's/,$//') ]
}
JSON
chmod 600 .preflight.json

echo ""
if [[ "$critical" -eq 1 ]]; then
  echo "PREFLIGHT: FAILED — critical host dependencies are missing. Fix and re-run."
  exit 1
fi
echo "PREFLIGHT: OK — host is ready for the setup wizard."
exit 0
