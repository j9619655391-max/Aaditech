#!/usr/bin/env bash
# ============================================================================
# fetch-agent-build.sh — build & pull Aaditech-Agent-Setup.exe from GitHub
# Actions, straight from the Ubuntu/Linux host (no Windows needed).
#
# The equivalent Windows path is agent-installer/build-agent-installer.ps1
# (builds the bundle locally). The portal also exposes the same trigger as
# POST /api/agent-installer/build (admin), which uses GITHUB_BUILD_PAT from
# infra/.env.
#
# Usage:
#   ./fetch-agent-build.sh [PAT] [owner/repo]
#
# PAT is read (in order) from: the first argument, the GITHUB_BUILD_PAT line
# of infra/.env, or $GITHUB_BUILD_PAT. It needs `actions: read+write` on the
# repo. Default repo: j9619655391-max/Aaditech (or GITHUB_REPO in .env).
# Output: infra/installers/Aaditech-Agent-Setup.exe (the /downloads mount).
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

REPO="${2:-j9619655391-max/Aaditech}"
PAT="${1:-}"
OUT="installers/Aaditech-Agent-Setup.exe"
WORKFLOW="build-agent-installer.yml"
GITHUB_API="https://api.github.com"

# ---- resolve PAT -------------------------------------------------------------
if [[ -z "$PAT" && -n "${GITHUB_BUILD_PAT:-}" ]]; then PAT="$GITHUB_BUILD_PAT"; fi
if [[ -z "$PAT" && -f .env ]]; then
  PAT="$(grep -E '^GITHUB_BUILD_PAT=' .env | head -1 | cut -d= -f2- | tr -d ' \r')"
fi
if [[ -z "$PAT" ]]; then
  echo "ERROR: no GitHub PAT. Pass it as the first argument, set GITHUB_BUILD_PAT in infra/.env, or set the env var." >&2
  exit 1
fi
if [[ -f .env ]]; then
  REPO="$(grep -E '^GITHUB_REPO=' .env | head -1 | cut -d= -f2- | tr -d ' \r' || true)"
  [[ -n "$REPO" ]] || REPO="j9619655391-max/Aaditech"
fi

GH_HEADERS=(-H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" -H "Authorization: Bearer $PAT")

echo "==> Triggering ${WORKFLOW} on ${REPO} ..."
curl -fs -X POST "${GH_HEADERS[@]}" \
  -H "Content-Type: application/json" \
  -d '{"ref":"main","inputs":{"wazuh_version":"4.9.0","zabbix_version":"6.4.20"}}' \
  "${GITHUB_API}/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches" || {
    echo "ERROR: workflow dispatch failed (check PAT permissions: actions: read+write)." >&2; exit 1; }

run_id=""
for _ in $(seq 1 15); do
  run_id="$(curl -fs "${GH_HEADERS[@]}" "${GITHUB_API}/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=1" \
    | python3 -c 'import sys,json; r=json.load(sys.stdin).get("workflow_runs") or []; print(r[0]["id"] if r else "")')"
  [[ -n "$run_id" ]] && break
  sleep 2
done
[[ -n "$run_id" ]] || { echo "ERROR: dispatched, but no run id appeared (check the Actions tab)." >&2; exit 1; }

echo "==> Waiting for run ${run_id} to finish ..."
for _ in $(seq 1 60); do
  state="$(curl -fs "${GH_HEADERS[@]}" "${GITHUB_API}/repos/${REPO}/actions/runs/${run_id}" \
    | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r.get("status") + ":" + (r.get("conclusion") or "running"))')"
  if [[ "$state" == completed:* ]]; then
    if [[ "$state" != "completed:success" ]]; then
      echo "ERROR: build failed ($state). See the Actions tab." >&2; exit 1
    fi
    break
  fi
  sleep 10
done

echo "==> Downloading artifact ..."
mkdir -p installers
art_id="$(curl -fs "${GH_HEADERS[@]}" "${GITHUB_API}/repos/${REPO}/actions/runs/${run_id}/artifacts" \
  | python3 -c 'import sys,json; a=json.load(sys.stdin).get("artifacts") or []; print(a[0]["id"] if a else "")')"
[[ -n "$art_id" ]] || { echo "ERROR: no artifact found for run ${run_id}." >&2; exit 1; }

curl -fsL "${GH_HEADERS[@]}" "${GITHUB_API}/repos/${REPO}/actions/artifacts/${art_id}/zip" -o /tmp/aaditech-agent.zip
python3 - "$OUT" <<'PY'
import os, sys, zipfile
dst = sys.argv[1]
with zipfile.ZipFile("/tmp/aaditech-agent.zip") as zf:
    for m in zf.namelist():
        if m.endswith("Aaditech-Agent-Setup.exe"):
            with zf.open(m) as src, open(dst, "wb") as out:
                out.write(src.read())
            print(f"Saved {dst} ({os.path.getsize(dst)} bytes)")
            break
    else:
        sys.exit("Artifact zip did not contain Aaditech-Agent-Setup.exe")
PY

echo "==> Done. The /downloads page on the portal now serves it."
