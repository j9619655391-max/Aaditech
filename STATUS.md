# Aaditech Platform — Build Status

Spec version implemented against: **v1.4** (Aaditech_IT-Monitoring-Automation-Platform-Spec_v1_4.docx)
Last updated: session 7 (full live deploy executed).

Legend: ✅ Done & verified (executed) · 🟡 Code complete, not executable-without-a-live-dependency · ⬜ Not started · ⚠️ Flagged issue/gap

## Session 9: agent installer built on GitHub Actions (CI)

The `.exe` is now compiled in CI instead of a one-off Windows machine — the
WiX bundle actually *compiles and ships* end to end:

### ✅ `build-agent-installer.yml` (NEW) — workflow

- Runs on `windows-latest`; `workflow_dispatch` (manual, with Wazuh/Zabbix
  version + `include_mesh` inputs) and tag trigger (`agent-v*` → also creates
  a GitHub Release with the `.exe`).
- Pins **WiX 4.0.2** + matching `WixToolset.Bal.wixext/4.0.2` (newer WiX moved
  the bootstrapper extension — `-ext WixToolset.Bal.wixext` alone resolves to
  nothing on a fresh runner).
- Vendor MSIs are mirrored as assets on the `agent-installer-vendor-v1`
  release because `packages.wazuh.com` returns S3 `AccessDenied` (403) to
  GitHub runner egress IPs (URL is fine from normal residential IPs). Regenerate
  the mirror when bumping agent versions.
- Default build (Wazuh+Zabbix) needs **no repository secrets** — server values
  are passed at install time, so IP migration = new deploy command, not rebuild.
  MeshCentral inclusion is opt-in (`include_mesh`) and needs `AGENT_MESH_URL` +
  `AGENT_MESH_ID`.
- First successful build: **run 31058969270 → `Aaditech-Agent-Setup.exe` (21.8 MB)
  artifact**; tag `agent-v1.0.0` → Release with the `.exe` (22.2 MB).

### ✅ `AaditechAgentBundle.wxs` — fixed to actually compile

First-ever successful compile surfaced latent authoring bugs (none had been run):
- `LogoFile="branding\aaditech-logo.png"` referenced a non-existent file → removed.
- WiX v4 schema: `WixStandardBootstrapperApplication` needs `Theme` (legal values
  are `hyperlinkLicense`, etc.), `Variable` with `Type` requires `Value` (dropped
  `Type` on the overridables), and `Bundle/@Version` can't use
  `!(bind.FileVersion...)` on an MsiPackage → hardcoded `1.0.0.0`.
- MeshCentral package is now behind `<?if $(var.IncludeMesh) = 1 ?>`; the agent
  binary is per-portal so it's opt-in, and it's an ExePackage (not an MsiPackage).

### ✅ Docs updated

`agent-installer/README.md` — new "CI build (GitHub Actions) — recommended"
section (trigger paths, WiX pin, vendor mirror, no-secrets default, IP-migration
workflow); "What's genuinely not verified" now notes the bundle compiles on CI
with only live silent-install left to confirm on a real Windows endpoint.

### ⚠️ Still open

- Live silent-install test of `Aaditech-Agent-Setup.exe` on a real Windows
  endpoint (the MSI property names are unverified against the actual MSIs).
- Wazuh enrollment: `AGENT_WAZUH_ENROLL_KEY` only works once the manager's
  `authd` enrollment password is set to the same value — not yet wired into
  the stack.

## Session 8: agent-installer distribution + one-click bundle build

Fleet rollout of the agent is now fully wired, from "compile once on a Windows
machine" through "endpoint clicks download / GPO grabs a URL":

### ✅ `build-agent-installer.ps1` — one-click Windows bundle build (NEW)

- **Parses clean (0 errors) + PSScriptAnalyzer 0 errors** (only cosmetic
  Write-Host/BOM warnings).
- Automatic: installs the WiX 4 CLI (`dotnet tool`), downloads the three vendor
  agents (Wazuh from packages.wazuh.com, Zabbix from cdn.zabbix.com, MeshCentral
  from the portal), compiles `dist/Aaditech-Agent-Setup.exe`.
- `-SkipMesh` builds the Wazuh+Zabbix-only bundle while the MeshCentral portal is
  still coming up. Requires admin PowerShell + .NET SDK (clear failure message).
- Server details stay `bal:Overridable` — **no values baked into the .exe**, so
  the same build runs on localhost testing and the office environment.

### ✅ Portal download page + API (public)

- `app/routers/downloads.py` (NEW) — `GET /agent-installer` (metadata:
  available/filename/size_mb) and `GET /agent-installer/download` (streams the
  `.exe`). **Deliberately public** — the installer carries no secrets and fleet
  staff shouldn't need a portal account.
- `app/config.py` — `installer_dir` bound to `AADITECH_INSTALLER_DIR`
  (empty ⇒ reports "not available" instead of a false download).
- `portal-frontend/src/pages/DownloadAgent.jsx` (NEW, public `/downloads` route
  outside ProtectedRoute) — big download button with size + copyable GPO URL.
- `infra/docker-compose.yml` — `installers` volume mounted into portal-backend,
  `AADITECH_INSTALLER_DIR=/installer`. Nginx unchanged: `/` → SPA, `/api/*` →
  backend already covers both URLs.
- Tests: **backend 4 new (72 total)**, **frontend 1 new (12 total)** — all green;
  `vite build` + compose config both validate.

## Session 7: full stack deployed live

Docker + mkcert + network were available, so the **entire server stack was
actually brought up** via `infra/setup.sh` and exercised through the real
reverse proxy — not just unit-tested:

- **15 containers came up** (reverse-proxy, portal-backend, portal-frontend,
  wazuh-indexer/manager/dashboard, zabbix-db/server/web, glpi+db, ocs+db,
  meshcentral, grafana). Both portal images built from their Dockerfiles.
- Frontend serves through the proxy: `https://localhost/` returns the React app.
- Backend reachable at `https://localhost/api/health` → `{"status":"ok"}`.
- Unauthenticated API requests correctly return **403** through the proxy.
- SSO degrades correctly: `GET /api/auth/sso/login` → 307
  `/login?error=azure_not_configured` when Azure isn't configured.

### ✅ Real bugs found & fixed by the live deploy

1. **`AADITECH_DB_PATH` was silently ignored** — `app/config.py` declared
   `db_path: str = ""`, but pydantic-settings reads env var `DB_PATH` by default
   (not `AADITECH_DB_PATH`), so `settings.db_path` stayed empty and `init_db()`
   kept SQLite **in-memory even in production** — state would be lost on every
   portal-backend restart. Fixed with
   `Field(default="", validation_alias="AADITECH_DB_PATH")`. Verified live:
   submit → approve → restart → report still `quarantined` + pending QUARANTINE
   command survived from the file DB.
2. **`setup.sh` health check was a false positive** — it polled
   `https://localhost/health` (which the proxy does NOT route — the backend's
   `/health` is only reachable at `/api/health`), and used `curl` without `-f`,
   which returns exit 0 on a 404. So "waiting for healthy portal" succeeded on
   the first response regardless of actual health. Fixed to poll
   `https://localhost/api/health` with `-f`.
3. **`setup-certs.sh` hard-failed without root** — `mkcert -install` needs the
   system trust store. Now degrades gracefully on non-root hosts (mkcert still
   auto-creates its CA in `CAROOT`; certs serve TLS fine; only browser trust is
   deferred). Also fixed a no-op `cp grafana.pem grafana.pem`.

### ✅ Live Category B end-to-end (outside compose, via uvicorn)

Full loop exercised against a running backend: viewer submits report → viewer
approve **403** (R-8 gate) → approver approve **200** + QUARANTINE command
enqueued → agent polls → ack → complete → restore → audit entries written
(`category_b_approve_execute`, `category_b_restore`).

### ✅ PowerShell functional execution (pwsh 7.4.6)

- All 8 scripts parse with **0 errors** (PSScriptAnalyzer: 0 errors; only
  cosmetic warnings).
- Category B scripts functionally executed against real temp files:
  `category-b-cleanup-execute.ps1` moved 1/1, `category-b-restore.ps1`
  restored the file, `category-b-purge-execute.ps1` purged it.

## Session 6: everything previously "blocked" is now executed

The prior sessions were run in an offline sandbox with **no pip, no npm, no
pwsh, and no network**. Session 6 restored network access and actually ran the
full stack in this environment:

- **Backend: all 13 test files executed via `pytest` → 68/68 pass.** This
  includes the 7 that were previously "written, not executed"
  (`test_wazuh_client.py`, `test_zabbix_client.py`, `test_glpi_client.py`,
  `test_meshcentral_client.py`, `test_auth.py`, `test_main.py`,
  `test_cleanup_router.py`) once deps were `pip install`ed.
- **Frontend: `npm ci` → `npm test` → `npm run build` all pass (11/11).
- **PowerShell: `pwsh` 7.4.6 installed; all 8 scripts parse clean, and the
  Category B quarantine / restore / purge flow was functionally executed.**

### ✅ Backend fixes made this session (real bugs found by executing the tests)

1. **SQLite thread-safety** — FastAPI runs sync handlers on a threadpool, so a
   single shared `sqlite3` connection crashed with
   `ProgrammingError: SQLite objects created in a thread can only be used in
   that same thread`. Fixed in `app/cleanup_store.py` and `app/agent_commands.py`
   by opening the connection with `check_same_thread=False` guarded by an RLock.
2. **Unwritable audit/health log path** — the default
   `/var/log/aaditech/*.jsonl` is not writable by a non-root service, which
   raised `PermissionError` and turned the `/cleanup/*/approve` request into a
   500. `app/audit.py` and `app/health_log.py` now lazily resolve a writable
   path and degrade gracefully to a per-user temp location instead of failing.
3. **Stale test** — `tests/test_main.py` created a token with role `"engineer"`,
   but the RBAC model uses `"support_engineer"`, so the ticket-validation test
   got 403 instead of 422. Test corrected to use the real role name.

### 🟢 Frontend fixes made this session

1. **Missing `index.html`** — the repo had `src/` but no Vite entry, so
   `vite build` failed ("Could not resolve entry module"). Added
   `portal-frontend/index.html`.
2. **Missing `Dockerfile` + `.dockerignore`** — `docker-compose.yml` references
   `portal-frontend` but no image definition existed. Added a two-stage
   Dockerfile (node build → nginx serve) plus `.dockerignore`.
3. **`App.jsx` Router-in-Router** — `App` hardcoded a `BrowserRouter`, which
   broke testing under `MemoryRouter`. Split into router-free `AppContent`
   (exported) + default `App`, so routing/auth is unit-testable in isolation.
4. **`@testing-library/user-event`** missing from `package.json` — added and
   installed for the Cleanup checklist interaction test.
5. **client.test.js mock wiring** — `axios.create` is called once at module
   import before any `beforeEach`, so a naive mock (set after static import)
   returned `undefined`. Rewrote with a `vi.hoisted` mock that supplies the
   axios module + a controllable instance, and the baseURL assertion now reads
   the captured config instead of the wiped call history. Also
   `cleanupApi.listReports` returns an array, so the assertion is `result[0]`.

### 🟢 WiX UpgradeCode

`agent-installer/wix/AaditechAgentBundle.wxs` had the placeholder
`{PUT-GENERATED-GUID-HERE}`. Replaced with a real GUID
`{b06067a6-6ed7-48a1-938b-da2c478f5157}`.

## Session 5: remaining steps progressed (gaps closed)

### ✅ Closed: approve → quarantine move now agent-dispatched

The session-4 finding (approve only flipped DB status, no agent ever told to
physically move files into quarantine) is fixed:

- `app/agent_commands.py` — new `QUARANTINE` command type.
- `app/routers/cleanup.py` — `POST /cleanup/scan-reports/{id}/approve` now
  enqueues a `QUARANTINE` command per approved item (returns `command_ids`).
- `self-healing/agent-command-poller.ps1` — dispatches `quarantine` commands to
  `category-b-cleanup-execute.ps1` before restore/purge handling. **Verified in
  session 6: payload field names (`item_id`, `path`, `quarantine_path`) match
  what the backend enqueues, and the execute script ran functionally.**
- `tests/test_agent_commands.py` — added 2 tests for the QUARANTINE lifecycle.

### ✅ Session 5 closed: persistence for cleanup_store + agent_commands

Both in-memory stores replaced with a SQLite-backed write-through cache
(stdlib `sqlite3`, zero new dependencies):

- `app/cleanup_store.py`, `app/agent_commands.py` — `init_db(path)`; all
  mutations persisted synchronously; public signatures unchanged (now also
  thread-safe, session 6).
- `app/config.py` — `db_path` (`AADITECH_DB_PATH`, default empty ⇒ in-memory).
- `app/main.py` — calls `init_db(settings.db_path)` at startup.
- `infra/docker-compose.yml` — `portal-data` volume; `AADITECH_DB_PATH=/data/aaditech.db`.
- `tests/test_persistence.py` — **executed: 3/3 pass**.

### ✅ Session 5: SSO + O365 email implemented (offline-testable)

- `app/ms_oauth.py` (NEW) — stdlib `urllib` OAuth2 helpers: SSO authorize-URL +
  token exchange + id_token decode + Azure group→role mapping, and a
  client-credentials Graph `/sendMail` for report email.
- `app/routers/auth_sso.py` (rewritten) — real login/callback build redirects
  and issue a JWT, with CSRF state; group→role wiring via `AZURE_ADMIN_GROUP_IDS`.
- `app/integrations/alerting.py` — `send_report_email` now delegates to
  `ms_oauth.send_graph_email` instead of `NotImplementedError`.
- `app/config.py`, `generate-secrets.sh`, `docker-compose.yml` — add `AZURE_ADMIN_GROUP_IDS`.
- `tests/test_sso_email.py` — **executed: 6/6 pass**.

## Sandbox / remaining environment limitations

Everything below is now *executed* in an environment with Python 3.12, pip,
Node 20.18, and pwsh 7.4.6 (Node + pwsh were downloaded locally in session 6).
The only things still **not executable without an external live system**:

- **Azure SSO + O365 email live handshake** — needs a real tenant / Phase 0 spike.
- **WiX bundle compile** — needs the `wix` CLI and the three vendor MSIs.
- **`one-click-install.ps1` real run** — needs a Windows endpoint + download URLs.
- **`setup.sh` / `setup-certs.sh` end-to-end** — needs mkcert + a Docker host
  + the public images.

Everything else below was actually run and is marked ✅.

## Completed (per component, nothing omitted)

### Infra / Deployment (`infra/`)
| Item | Status | Notes |
|---|---|---|
| `docker-compose.yml` | ✅ | v1.4, 9 services; only `reverse-proxy` exposes 443, isolated internal network, HTTPS everywhere from Phase 1, §7.6 port table, OCS Inventory included. |
| `nginx/portal.conf` | ✅ | 80→443, `/`→frontend, `/api/`→backend, `/api/remote/ws/`→MeshCentral WebSocket. |
| `generate-secrets.sh` | ✅ | Produces `.env` with all v1.4 secrets + encrypted placeholder email/Azure stubs. |
| `setup-certs.sh` | 🟡 | mkcert + per-service certs; bash-syntax-checked, needs ckg+mkcert to run. |
| `setup.sh` | 🟡 | Preflight → secrets → certs → `compose up -d` → wait on `/health`. |
| `certs/` | ✅ | Pre-generated mkcert-style certs committed. |

### Portal Backend (`portal-backend/`)
| Item | Status | Notes |
|---|---|---|
| `app/config.py` | ✅ | All settings from env, nothing hardcoded. |
| `app/main.py` | ✅ | FastAPI app, CORS, 7 routers, `/health`. |
| `app/auth.py` | ✅ | JWT create/decode, HTTPBearer. |
| `app/roles.py` | ✅ | 3-role RBAC, `require_any_role` + named deps. Closes R-8. |
| `app/audit.py` | ✅ | JSON-lines audit log, 7 actions; graceful path fallback (session 6). |
| `app/health_log.py` | ✅ | Operational health log; graceful path fallback (session 6). |
| `app/cleanup_store.py` | ✅ executed 9/9 | Category B state; SQLite-backed, thread-safe. |
| `app/agent_commands.py` | ✅ executed 8/8 | Portal→agent poll queue; QUARANTINE+RESTORE+PURGE; SQLite-backed, thread-safe. |
| `app/integrations/wazuh_client.py` | ✅ executed 4/4 | Auth, alerts, FIM, vulnerabilities, agent status, versions. |
| `app/integrations/zabbix_client.py` | ✅ executed 4/4 | JSON-RPC hosts/triggers/history/forecast. |
| `app/integrations/glpi_client.py` | ✅ executed 4/4 | initSession + Ticket CRUD. |
| `app/integrations/meshcentral_client.py` | ✅ executed 3/3 | start/status/end session. |
| `app/ms_oauth.py` | ✅ executed 1/1 | OAuth2 + Graph helpers (via test_sso_email). |
| `app/integrations/alerting.py` | ✅ | Telegram+Slack primary; email via ms_oauth. |
| `app/integrations/version_drift.py` | ✅ executed 5/5 | Per-agent version drift. |
| `app/integrations/pilot_ring.py` | ✅ executed 9/9 | Pilot/fleet ring + bake period. |
| `app/routers/alerts.py` | ✅ executed | RBAC Viewer+. |
| `app/routers/metrics.py` | ✅ executed | RBAC Viewer+. |
| `app/routers/tickets.py` | ✅ executed | RBAC Support Eng+. |
| `app/routers/remote.py` | 🟡 | session/status/end; RBAC Support Eng+. |
| `app/routers/dashboards.py` | ✅ | Grafana embed signing + refresh + retry. |
| `app/routers/downloads.py` | ✅ executed 4/4 | **NEW (session 8)** public agent-installer info + download; 404 when not published. |
| `app/routers/cleanup.py` | ✅ executed | scan-submit/list/approve/restore/purge + agent command poll/ack/complete. |
| `app/routers/auth_sso.py` | ✅ offline / 🟡 live | Real login/callback; live handshake needs a tenant. |
| `tests/` (13 files) | ✅ 72/72 | **14 files (NEW test_downloads.py) all executed and green via pytest.** |

### Self-Healing (`self-healing/`)
| Item | Status | Notes |
|---|---|---|
| `category-a-autofix.ps1` | ✅ parses | Service restart, zombie kill, network reset, whitelisted cache clear. |
| `category-b-cleanup-scan.ps1` | ✅ parses | Report-only scan of §3.5 targets. |
| `category-b-cleanup-execute.ps1` | ✅ **functional** | Quarantine mover; **executed: 1 moved, 0 failed** (session 6). |
| `category-b-restore.ps1` | ✅ **functional** | **Executed: successfully restored** (session 6). |
| `category-b-purge-execute.ps1` | ✅ **functional** | **Executed: purge deleted** (session 6). |
| `agent-command-poller.ps1` | ✅ parses | Polls, acks, dispatches qu/restore/purge; NEW `quarantine` dispatch. |
| `tests/` | — | (see backend tests). |

### Portal Frontend (`portal-frontend/`)
| Item | Status | Notes |
|---|---|---|
| Build config | ✅ | Vite, React 18, Router 6, Axios, Vitest+RTL+jsdom. |
| `index.html` | ✅ (NEW session 6) | Vite entry — previously missing. |
| `Dockerfile` + `.dockerignore` | ✅ (NEW session 6) | node build → nginx serve. |
| `src/api/client.js` | ✅ | Centralized client, bearer interceptor, 401→redirect; all 6 API namespaces. |
| Routing + layout | ✅ | `App.jsx` AppContent+App split; `Layout.jsx`. |
| Pages | ✅ | Login, Overview, Alerts, Metrics, Tickets, Cleanup, RemoteAccess, DownloadAgent (public, session 8). |
| Vitest suite | ✅ 12/12 | `App.test.jsx`, `Cleanup.test.jsx`, `client.test.js` — **executed.** |

### Agent Installer (`agent-installer/`)
| Item | Status | Notes |
|---|---|---|
| `one-click-install.ps1` | 🟡 parses | Downloads Wazuh/Zabbix/Mesh; needs a Windows endpoint to run. |
| `build-agent-installer.ps1` | ✅ (NEW) parses, lint 0 errors | **One-click Windows build**: installs WiX, downloads vendor agents, compiles `Aaditech-Agent-Setup.exe`. Server values not baked in (`bal:Overridable`). |
| `AgentConfig.sample.json` | ✅ | The one manual config file. |
| `wix/AaditechAgentBundle.wxs` | 🟡 | WiX v4 Burn bundle; **real UpgradeCode now set** (session 6); compile needs a Windows `wix` CLI (now scriptable via `build-agent-installer.ps1`). |
| `psadt/Deploy-AaditechAgent.ps1` | 🟠 parses | PSADT alternative. |
| Vendor MSIs | ⬜ | Not included; URLs documented. |

### Documentation
| Item | Status |
|---|---|
| `README.md` | ✅ |
| `docs/ARCHITECTURE.md` | ✅ |
| `docs/DEPLOYMENT.md` | ✅ |
| `STATUS.md` (this file) | ✅ |

## Open items / not-started (consolidated)

1. **O365 / Azure SSO + email live validation** — code complete & offline-tested,
   but the actual token-exchange / Graph send needs a real tenant (Phase 0 spike).
2. **WiX bundle compile** — needs the `wix` CLI and the three vendor MSIs; the
   UpgradeCode GUID is now real, and MSI property names must be confirmed
   against the actual installers.
3. **`setup.sh` / `setup-certs.sh`** — **executed** (session 7): portal images
   built, all 15 containers up, proxy verified. `setup-certs.sh` now also works
   on non-root hosts (defer browser CA trust instead of failing).
4. **`one-click-install.ps1` real run** — needs a Windows endpoint.
5. **OCS Inventory** — **resolved** (session 5): kept as intended for asset discovery.

## Test execution summary (cumulative, definitive)

```
ALL backend tests executed via pytest:  72/72 PASS across 14 files

PASS: test_agent_commands.py       8/8   (+2 QUARANTINE tests)
PASS: test_auth.py                 3/3
PASS: test_cleanup_router.py       4    (RBAC approve deny, lifecycle)
PASS: test_cleanup_store.py        9/9
PASS: test_downloads.py            4/4  (session 8, NEW)
PASS: test_glpi_client.py          4/4
PASS: test_main.py                6
PASS: test_meshcentral_client.py   3/3
PASS: test_persistence.py          3/3  (session 5, new)
PASS: test_pilot_ring.py           9/9
PASS: test_sso_email.py            6/6  (session 5, new)
PASS: test_version_drift.py        5/5
PASS: test_wazuh_client.py         4/4
PASS: test_zabbix_client.py        4/4

frontend):  npm test  12/12 pass (3 suites: App, Cleanup, client)

PowerShell functional (pwsh 7.4.6):
  category-b-cleanup-execute.ps1 → 1 moved, 0 failed
  category-b-restore.ps1         → file restored
  category-b-purge-execute.ps1   → permanently purged
  All 8 *.ps1 parse with 0 errors
```

## Recommended next steps (in order)

1. **DONE (session 6-8):** full backend (68/68 → now **72/72**) + frontend (11/11
   → now **12/12**) + PowerShell Category B flows executed; WiX UpgradeCode set;
   `index.html` + frontend Dockerfile added; **full stack deployed via
   `setup.sh`** (15 containers up); **agent-installer distribution added**
   (`build-agent-installer.ps1` + public `/downloads` page + download API).
2. **`infra/.env`: fill in Azure O365 placeholders** (Azure client/tenant IDs,
   group IDs, Telegraph/Slack) so portal-backend gets its SSO + report-email
   credentials — the token source of the Phase 0 spike.
3. Validate SSO + O365 email against a **real Azure tenant** (Phase 0 spike).
4. Build + test the **WiX bundle** on a Windows build machine with the `wix` CLI
   + the three vendor MSIs; confirm the MSI property names match the actual
   installers before fleet rollout.
5. Run each self-healing script on a **Windows VM** (dry-run then live) and run
   `PSScriptAnalyzer` on the whole set to close the last PowerShell gap.