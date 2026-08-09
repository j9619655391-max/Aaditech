# Aaditech IT Monitoring & Automation Platform

Implements spec v1.4. Two machine roles — read this before running anything:

| | Runs on | One-click entry point |
|---|---|---|
| **Server stack** (Wazuh, Zabbix, GLPI, MeshCentral, Grafana, Portal) | **Your Ubuntu Docker host** | `cd infra && ./install.sh` — git pull, then this one command: a setup wizard page (company, admin login, local IP, notification email) generates all tokens/certs/keys automatically, then the full stack comes up |
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
│   ./install.sh — one cmd │◄───────►│   .\one-click-install.ps1 │
│   (setup wizard → full   │  agent  │   Wazuh agent, Zabbix     │
│   stack + all services)  │ traffic │   agent, MeshCentral      │
└─────────────────────────┘         └──────────────────────────┘
```

## Quick start

**1. Server (Ubuntu):**
```bash
cd infra
./install.sh
```
One command. It first runs a **host preflight** (docker, compose v2, openssl,
curl, free ports, disk) and prints a PASS/FAIL report. Then it starts a
one-time **setup wizard** at `http://localhost:8080/setup` where you enter
company name, admin login, the server IP, and pick **notification channels**
— email (provider auto-configured: gmail / hotmail / office365 / hostinger,
app-password ready for MFA), Telegram (bot token + chat ID) and/or MS Teams
(webhook). An optional **GitHub PAT** lets the portal build the agent `.exe`
via Actions. All service tokens, certificates, endpoints and the agent
enrollment key are generated automatically on submit — before that, `infra/.env`
is deliberately blank. Then the full stack comes up. Details:
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
- `docs/AZURE_SSO_EMAIL.md` — Azure AD SSO + Office 365 email testing checklist (SMTP/MFA, Graph, app registration)
- `STATUS.md` — build status, what's verified vs. not, what's still open
- `Aaditech_IT-Monitoring-Automation-Platform-Spec_v1_4.docx` — the source spec
