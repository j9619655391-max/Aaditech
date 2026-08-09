# Architecture

This describes how the built code (`portal-backend/`, `portal-frontend/`,
`self-healing/`, `agent-installer/`, `infra/`) implements spec v1.4. For
*why* each decision was made, see the spec itself
(`Aaditech_IT-Monitoring-Automation-Platform-Spec_v1_4.docx`) — this doc
covers *what was built* and *where*.

## Component map

```
                         ┌─────────────────────┐
  End users / engineers  │   portal-frontend    │  https://localhost (only URL anyone browses)
  ─────────────────────► │   (React, RBAC UI)   │
                         └──────────┬───────────┘
                                    │ REST (JWT bearer)
                         ┌──────────▼───────────┐
                         │   portal-backend      │  FastAPI, single service
                         │   (app/)              │
                         └─┬────┬────┬────┬─────┬┘
                    Wazuh  │Zabbix│GLPI│Mesh│Grafana
                     API   │ API  │REST│ API│ embed
                    ┌──────▼┐┌───▼──┐┌─▼──┐┌▼───┐┌────▼───┐
                    │ Wazuh ││Zabbix││GLPI││Mesh││Grafana │  isolated Docker
                    │       ││ +DB  ││+DB ││Cent││(hidden)│  network, no
                    └───────┘└──────┘└────┘└────┘└────────┘  public ports

  Endpoints  ──agent traffic (1514/1515/10050/10051/4433)──►  Wazuh/Zabbix/Mesh managers
  (Aaditech         ▲
   Agent bundle)     │ poll (restore/purge commands)
                      └────────────────  portal-backend  (app/agent_commands.py)
```

## portal-backend layout

| Path | Responsibility |
|---|---|
| `app/main.py` | FastAPI app assembly, router registration |
| `app/config.py` | All settings from environment (`.env`) — nothing hardcoded |
| `app/auth.py` | JWT issuance/validation |
| `app/roles.py` | RBAC — Viewer / Support Engineer / Cleanup Approver (§7.1, closes R-8) |
| `app/audit.py` | Structured audit log → forwarded to Wazuh/OpenSearch (§7.4) |
| `app/health_log.py` | Agent/panel health tracking (§7.1.1, §7.2.1) |
| `app/cleanup_store.py` | Category B scan-report / quarantine state (§3.5) |
| `app/agent_commands.py` | Portal→agent command queue — how restore/purge actually reach the endpoint (see below) |
| `app/integrations/` | One client per backend tool, plus `version_drift.py` and `pilot_ring.py` |
| `app/routers/` | One router per feature area, each RBAC-gated per `roles.py` |

## Category B: scan → report → approve → quarantine → execute → restore/purge

This is the safety-critical path (spec §3.5) — no destructive action
without explicit human approval. Sequence:

1. `self-healing/category-b-cleanup-scan.ps1` runs on the endpoint, reports
   findings only (never deletes) → `POST /cleanup/scan-reports`
2. Engineer reviews the checklist in the portal UI
   (`portal-frontend/src/pages/Cleanup.jsx`), unchecks anything to keep
3. Engineer with the **Cleanup Approver** role clicks Approve & Execute →
   `POST /cleanup/scan-reports/{id}/approve` → `cleanup_store.approve_items()`
   computes the off-volume quarantine path and hold expiry (standard 7-day
   or emergency 24-hour, per §3.5 v1.2), and **enqueues a `QUARANTINE`
   command per approved item** in `app/agent_commands.py` (returns
   `command_ids`).
4. The endpoint's poller (`agent-command-poller.ps1`) picks up each
   `quarantine` command and dispatches it to
   `self-healing/category-b-cleanup-execute.ps1`, which moves the approved
   items into the quarantine volume on the endpoint.
5. Within the hold window, an engineer can restore an item:
   `POST /cleanup/items/{report_id}/{item_id}/restore` flips DB status
   **and** enqueues a command in `app/agent_commands.py`
6. `self-healing/agent-command-poller.ps1` (scheduled on the endpoint)
   polls `GET /cleanup/agent/{endpoint_id}/commands`, acks the command,
   runs `category-b-cleanup-execute.ps1` (quarantine),
   `category-b-restore.ps1` (restore) or `category-b-purge-execute.ps1`
   (purge) depending on command type, then reports success/failure back via
   `POST /cleanup/agent/commands/{id}/complete`
7. At window expiry, the ILM cron job calls `POST /cleanup/purge-expired`,
   which enqueues PURGE commands the same way restore does

The whole loop (quarantine → restore → purge) is wired end-to-end via a
simple poll queue (`app/agent_commands.py` + `agent-command-poller.ps1`)
rather than Wazuh active-response, reusing the HTTPS channel the agent
already uses for scan-report submission. The `quarantine` dispatch was added
in session 5 after the session-4 audit flagged step 4 as a gap.

## Persistence (added session 5)

`app/cleanup_store.py` and `app/agent_commands.py` no longer use in-memory
dicts. Both are now a **write-through cache over SQLite** (stdlib
`sqlite3`, zero new dependencies):

- every mutation is synchronously persisted, so a container restart loses
  nothing;
- by default the DB is in-memory (`AADITECH_DB_PATH` unset — preserves the
  dev/test behaviour); set `AADITECH_DB_PATH` to a path on a persistent
  volume for production (docker-compose.yml mounts `portal-data` at
  `/data`, with `AADITECH_DB_PATH=/data/aaditech.db`);
- the public function signatures are unchanged, so swapping to a heavier
  store (e.g. Postgres alongside the other service DBs) later still only
  touches these two files (call `init_db(path)` at startup, done in
  `app/main.py`).

## RBAC model

Three roles, additive (§7.1, v1.2):

- **Viewer** — read-only dashboards/alerts, plus the agent service
  credential used for scan-report submission and command polling
- **Support Engineer** — Viewer + ticketing + MeshCentral sessions +
  Category A visibility
- **Cleanup Approver** — Support Engineer + Category B approve/restore
  (closes risk R-8: a plain SSO login is not sufficient for fleet-wide
  deletion actions)

## Agent version drift & phased rollout (§7.2.1)

- `app/integrations/version_drift.py` — per-agent drift vs. expected
  version, `GET /alerts/agent-versions`
- `app/integrations/pilot_ring.py` — deterministic pilot/fleet ring
  assignment + bake-period gating, `GET /alerts/rollout-plan`. Fleet stays
  blocked until the pilot ring has soaked for the configured bake period
  *and* shows no drift/failure — not just until the timer expires.

## Known deviations from "fully built"

- **Resolved session 6 (superseded):** with network restored, the full backend
  test suite now runs (`pip install -r requirements.txt` then `pytest` —
  68/68 at the time, **105/105 as of session 11**), all 8 `self-healing/*.ps1`
  scripts parse clean under pwsh 7.4.6 and the Category B
  quarantine/restore/purge flow was functionally executed, and the frontend
  `npm ci`/`npm test`/`npm run build` all succeed. Two backend bugs surfaced
  by actually executing the tests were fixed: SQLite thread-safety
  (`check_same_thread=False` + RLock in `cleanup_store.py` /
  `agent_commands.py`), and the unwritable `/var/log/aaditech` default path
  in `app/audit.py` / `app/health_log.py` (now degrades gracefully to a
  per-user temp location instead of 500ing).
- `agent-installer/` ships the WiX bundle definition and PSADT script, but
  not the vendor MSIs themselves (must be downloaded separately) — see
  `agent-installer/README.md`. The WiX `UpgradeCode` is a real GUID now.
- The Category B command loop is fully wired end-to-end (quarantine/restore/
  purge, session 5) and `cleanup_store.py` / `agent_commands.py` are now
  SQLite-persisted and thread-safe — both previously-flagged deviations are
  resolved.
- Azure AD SSO (`auth_sso.py`) and O365 email (`alerting.send_report_email`)
  are implemented against Microsoft's live endpoints (OAuth2, stdlib in
  `app/ms_oauth.py`) but **not exercised against a real tenant** — they
  return a clear error/`False` when Azure settings are absent, and the
  token-exchange + Graph calls themselves still need the Phase 0 Azure
  spike to validate against a live tenant (see `docs/DEPLOYMENT.md`).
