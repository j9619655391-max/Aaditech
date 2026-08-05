# Aaditech IT Monitoring & Automation Platform

Implements spec v1.4. Two machine roles — read this before running anything:

| | Runs on | One-click entry point |
|---|---|---|
| **Server stack** (Wazuh, Zabbix, GLPI, MeshCentral, Grafana, Portal) | **Your Ubuntu Docker host** | `cd infra && ./setup.sh` |
| **Agent** (Wazuh/Zabbix/MeshCentral endpoint components) | **Each Windows PC being monitored** | `cd agent-installer && .\one-click-install.ps1` |

These are not two halves of the same install — they're two different
machines by design, because this platform *monitors a Windows desktop
fleet from a Linux server*. The PowerShell scripts under `self-healing/`
and `agent-installer/` run on the Windows PCs being managed, never on your
Ubuntu box; nothing in `infra/` or `portal-backend/` needs Windows or
PowerShell at all.

```
┌─────────────────────────┐         ┌──────────────────────────┐
│   Ubuntu Docker host     │ HTTPS   │   Windows endpoint(s)     │
│   ./setup.sh — one cmd   │◄───────►│   .\one-click-install.ps1 │
│   Portal, Wazuh, Zabbix, │  agent  │   Wazuh agent, Zabbix     │
│   GLPI, MeshCentral,     │ traffic │   agent, MeshCentral      │
│   Grafana (all Docker)   │         │   agent (all installed)   │
└─────────────────────────┘         └──────────────────────────┘
```

## Quick start

**1. Server (Ubuntu):**
```bash
cd infra
./setup.sh
```
One command — generates secrets, sets up HTTPS certs, brings up every
container, waits for the portal to be healthy. Details:
`docs/DEPLOYMENT.md`.

**2. Each Windows endpoint:**
```powershell
cd agent-installer
Copy-Item AgentConfig.sample.json AgentConfig.json
notepad AgentConfig.json    # fill in manager IP, enrollment key, mesh ID — one time
.\one-click-install.ps1
```
Details, and the fleet-wide GPO/Intune path: `agent-installer/README.md`.

## Everything else

- `docs/ARCHITECTURE.md` — component map, full Category B approval flow, RBAC model
- `docs/DEPLOYMENT.md` — step-by-step, test-running instructions, open items
- `STATUS.md` — build status, what's verified vs. not, what's still open
- `Aaditech_IT-Monitoring-Automation-Platform-Spec_v1_4.docx` — the source spec
