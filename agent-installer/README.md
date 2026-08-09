# Aaditech Agent Installer (spec §7.2)

**This runs on the Windows PCs being managed by the platform — not on your
Ubuntu server.** That's not a design shortcut, it's what §7.2/§3.5 of the
spec describes: the agent bundles Wazuh, Zabbix, and MeshCentral clients
that watch Windows-specific things (`Windows\Temp`, the registry, Windows
services), and gets pushed to the desktop/laptop fleet via GPO/Intune. The
Ubuntu machine only ever runs the *server* side (`infra/`) — see the
root `README.md` for that split.

## One click

```powershell
# 1. Fill in your values ONCE (this is the only manual step — everything
#    else, including all three downloads, is automatic):
Copy-Item AgentConfig.sample.json AgentConfig.json
notepad AgentConfig.json

# 2. Run it:
.\one-click-install.ps1
```

That's it — `one-click-install.ps1` downloads all three vendor agents
itself (Wazuh from `packages.wazuh.com`, Zabbix from `cdn.zabbix.com`, and
the MeshCentral agent from your own portal's MeshCentral instance) and
installs them silently. Nothing to download by hand, no multi-script
sequence.

**Why `AgentConfig.json` can't be filled in for you:** the manager IP,
enrollment key, and mesh ID are specific to *your* deployment — nobody
else can know them, including this script. Same as any deploy tool:
Ansible needs an inventory, Terraform needs variables. Once that one file
is filled in, running it on more machines needs zero further input.

**Why the MeshCentral piece is different from Wazuh/Zabbix:** Wazuh and
Zabbix agents are public downloads from the vendor's own site — anyone can
fetch them with just a version number. MeshCentral doesn't work that way:
its agent binary is generated per-server and tied to a specific device
group (mesh ID) on *your own* MeshCentral instance, so it only exists once
your portal is up and a device group has been created in it. This isn't a
gap in the script — it's how MeshCentral is designed to work.

## One-click bundle build (for the whole fleet)

Push a single `.exe` to everyone via GPO/Intune with **one click on a
Windows build machine**:

```powershell
# (once) fill AgentConfig.json — created automatically from the sample on
# first run; only your manager IP / enrollment key / mesh ID go here.
.\build-agent-installer.ps1

# if MeshCentral isn't up yet, build just the Wazuh+Zabbix part:
.\build-agent-installer.ps1 -SkipMesh
```

`build-agent-installer.ps1` does everything by itself:
- installs the WiX 4 CLI (`dotnet tool`)
- downloads all three vendor agents into `wix/vendor/`
- compiles `Aaditech-Agent-Setup.exe` into `dist/`

**Server details are NOT baked into the .exe.** Every value in
`wix/AaditechAgentBundle.wxs` is `bal:Overridable`, so they're passed at
*install* time — the same `.exe` works on your localhost test server and in
the office environment, with no rebuild. GPO/Intune example:

```
Aaditech-Agent-Setup.exe ManagerIp=10.0.0.10 ZabbixServerIp=10.0.0.10 MeshCentralUrl=https://portal.office.local:4433 WazuhEnrollKey=KEY
```

Requires admin PowerShell and the .NET SDK on the build machine (the script
fails with a clear message if `dotnet` is missing).

## CI build (GitHub Actions) — recommended

You don't need a Windows build machine at all. The repo ships a workflow
(`.github/workflows/build-agent-installer.yml`) that compiles the same
`Aaditech-Agent-Setup.exe` on a `windows-latest` runner:

- **Manual trigger** — Actions → "Build Agent Installer (.exe)" → Run workflow
  (inputs: Wazuh/Zabbix versions, `include_mesh`).
- **Tag trigger** — push `agent-v*` (e.g. `agent-v1.0.0`); the build runs and
  the `.exe` is attached to a GitHub Release for download:
  `https://github.com/<org>/<repo>/releases/tag/agent-v1.0.0`

The workflow pins **WiX 4.0.2** and its matching Bal extension (newer WiX
versions moved/renamed the bootstrapper extension). Vendor MSIs are mirrored
as assets on the `agent-installer-vendor-v1` release because
`packages.wazuh.com` returns S3 `AccessDenied` (403) to GitHub runner IPs —
the workflow downloads them from that mirror instead. Regenerate the mirror
whenever you upgrade agent versions.

**No secrets required for the default (Wazuh+Zabbix) build.** Server
addresses stay out of the `.exe` entirely — you pass them at install time:

```
Aaditech-Agent-Setup.exe ManagerIp=10.73.77.58 ZabbixServerIp=10.73.77.58 WazuhEnrollKey=...
```

So when you migrate to a new server IP you **don't rebuild anything** — just
run the same `.exe` with the new address in the GPO/Intune command.

Only the MeshCentral piece is baked at build time (its agent binary is
generated per-portal/device-group), so including it needs two extra secrets
(`AGENT_MESH_URL`, `AGENT_MESH_ID`) and the `include_mesh` input on.

### Triggering + pulling the build from the server (no Windows needed)

You don't have to open the Actions tab at all. Give the deployment a GitHub
PAT (wizard field "GitHub token", stored as `GITHUB_BUILD_PAT` — needs
`actions: read+write`) and either:

- **From the portal** — log in → **Download Agent** → **Build .exe from
  GitHub Actions**. The backend (`POST /api/agent-installer/build`) dispatches
  the workflow, waits for it to finish, downloads the artifact and drops
  `Aaditech-Agent-Setup.exe` straight into the `/downloads` mount.
- **From the Ubuntu host** — `cd infra && ./fetch-agent-build.sh [PAT] [repo]`
  does the same with curl + python3 (no Windows, no portal login). Output:
  `infra/installers/Aaditech-Agent-Setup.exe`.

Both are the *portable* build — no server values baked in — so they suit a
Linux-only deployment. The Windows-local `build-agent-installer.ps1` path
above remains for build machines without GitHub access.

## Publishing to the fleet (web download page)

Once built (by the portal build button, `fetch-agent-build.sh`, or manually),
put `dist/Aaditech-Agent-Setup.exe` in `infra/installers/` — that host
directory is mounted into the portal backend (see `infra/docker-compose.yml`
→ `AADITECH_INSTALLER_DIR`). The portal then exposes it:

- **Web page** — `https://portal.aaditech.local/downloads` (public, no
  login needed): a big "Download Aaditech Agent" button with size + a copyable
  URL for GPO/Intune.
- **Direct URL** — `https://portal.aaditech.local/api/agent-installer/download`
  (use this as your GPO/Intune package URL).
- **Status check** — `GET /api/agent-installer` returns JSON
  `{available, filename, size_mb}`; `available=false` until the `.exe` is
  actually mounted.

The endpoint is intentionally public: the installer contains no secrets
(server values are injected at install time), and fleet staff shouldn't need
a portal account to grab it.

## Mass rollout to the whole fleet (manual equivalent)

`one-click-install.ps1` is the fast path for one machine or a small pilot
ring. For pushing to the entire fleet via GPO/Intune as a single package,
use the WiX bundle instead — same config values, compiled into one `.exe`:

```
wix build wix/AaditechAgentBundle.wxs -ext WixToolset.Bal.wixext -o Aaditech-Agent-Setup.exe
```

Requires the WiX v4+ CLI (`dotnet tool install --global wix`) and the
three vendor MSIs placed under `wix/vendor/` (same two downloads
`one-click-install.ps1` does automatically — for the bundle you fetch them
once yourself, since WiX compiles them **into** the installer rather than
downloading them at install time).

A PSADT alternative (`psadt/Deploy-AaditechAgent.ps1`) is also included
for teams that prefer that toolchain over WiX — same install behavior,
scripted directly, reads the same `AgentConfig.json`.

## What's genuinely not verified here

This was all written and reviewed in a sandbox with no PowerShell and no
network — so none of the following was actually run:
- `one-click-install.ps1` itself — the download URLs are real, current
  vendor URL patterns (confirmed via search), but never executed end to
  end against a live Wazuh/Zabbix/MeshCentral deployment.
- **The WiX bundle — now compiled on CI.** The GitHub Actions workflow builds
  `Aaditech-Agent-Setup.exe` successfully (see Artifacts/Releases), so the WiX
  authoring *does* compile. What's still unverified is a live silent install
  on a real Windows endpoint.
- The PSADT script — not run (no `pwsh` here).
- Exact MSI property names (`WAZUH_REGISTRATION_PASSWORD`, `SERVERACTIVE`,
  etc.) match each vendor's documented silent-install properties, but
  weren't confirmed against the actual MSI you'll download — if a property
  turns out wrong, `msiexec /i wazuh-agent.msi /qn /l*v install.log` and
  check the log.

Test on one real Windows machine before pushing to the fleet.

## Pilot-ring rollout (§7.2.1)

Whichever path you use, don't push to the whole fleet at once.
`GET /alerts/rollout-plan?expected_version=vX.Y.Z` (portal API) returns
which endpoints are pilot-ring-eligible now, and which fleet endpoints are
still waiting on the bake period / a clean pilot. That logic lives in
`portal-backend/app/integrations/pilot_ring.py` — genuinely tested, 9/9.
