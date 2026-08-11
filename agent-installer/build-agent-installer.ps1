#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Aaditech Agent Installer — ONE-CLICK BUILD (run once on a Windows machine)

    Does everything automatically:
      1. Ensures the WiX 4 CLI is installed (dotnet tool)
      2. Downloads the three vendor agents (Wazuh, Zabbix, MeshCentral) into
         wix/vendor/
      3. Compiles them into a single branded installer: Aaditech-Agent-Setup.exe

.DESCRIPTION
    This is the "compile the bundle" step. You run it ONCE on any Windows
    machine with internet; the output .exe is then uploaded to your portal
    download page and pushed to the fleet via GPO/Intune.

    Server details are NOT baked into the .exe — every value in
    wix/AaditechAgentBundle.wxs is bal:Overridable. They are injected at
    INSTALL time from the command line / config, so the SAME .exe works on
    localhost testing and in the office environment. No rebuild needed.

    Before running: fill AgentConfig.json (created from the sample on first
    run). Only your manager IP, enrollment key and mesh ID are needed —
    everything else is downloaded automatically.

.PARAMETER SkipMesh
    If your MeshCentral portal isn't up yet (or you want to build the
    Wazuh+Zabbix part first), pass -SkipMesh to build without it. MeshCentral
    can be installed separately on endpoints later.
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "AgentConfig.json"),
    [string]$OutputDir = (Join-Path $PSScriptRoot "dist"),
    [switch]$SkipMesh
)

$ErrorActionPreference = "Stop"
$script:out = @()

function Write-Step { param([string]$Msg) Write-Host "  -> $Msg" -ForegroundColor Cyan }

# ---------------------------------------------------------------------------
# 1. Config
# ---------------------------------------------------------------------------
Write-Host "== Aaditech Agent — One-Click Build ==" -ForegroundColor Green
if (-not (Test-Path $ConfigPath)) {
    $sample = Join-Path $PSScriptRoot "AgentConfig.sample.json"
    if (Test-Path $sample) {
        Copy-Item $sample $ConfigPath
        Write-Step "created $ConfigPath from sample — open it and fill your values, then re-run."
        exit 0
    } else { throw "No AgentConfig*.json found in $PSScriptRoot" }
}
$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json

# ---------------------------------------------------------------------------
# 2. Prerequisites: dotnet + WiX CLI
# ---------------------------------------------------------------------------
Write-Step "Checking prerequisites (dotnet, wix)..."
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw ".NET SDK not found. Install it from https://dotnet.microsoft.com/download then re-run (admin)."
}

$env:Path = "$env:USERPROFILE\.dotnet\tools;$env:Path"
if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
    Write-Step "Installing WiX v4 CLI (dotnet tool wix)..."
    dotnet tool install --global wix 2>$null
    if ($LASTEXITCODE -ne 0) { dotnet tool update --global wix 2>$null }
    if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
        throw "WiX CLI install failed. Re-open a fresh terminal so $env:USERPROFILE\.dotnet\tools is on PATH, then re-run."
    }
}
Write-Step "wix version: $(& wix --version)"

# ---------------------------------------------------------------------------
# 3. Download vendor agents
# ---------------------------------------------------------------------------
$vendorDir = Join-Path $PSScriptRoot "wix\vendor"
New-Item -ItemType Directory -Path $vendorDir -Force | Out-Null

$wazuhVer = $config.wazuhAgentVersion
$zbxVer   = $config.zabbixAgentVersion
$zbxMM    = (($zbxVer -split '\.')[0..1] -join '.')

# Canonical names the WXS bundle references (wix/AaditechAgentBundle.wxs).
# Downloading to these exact names keeps the local build in sync with the
# CI path (which also stages unversioned vendor\*.msi files).
$wazuhMsi  = Join-Path $vendorDir "wazuh-agent.msi"
$zbxMsi    = Join-Path $vendorDir "zabbix-agent.msi"
$meshExe   = Join-Path $vendorDir "meshcentral-agent.exe"

if (-not (Test-Path $wazuhMsi)) {
    Write-Step "Downloading Wazuh agent ($wazuhVer)..."
    Invoke-WebRequest -Uri "https://packages.wazuh.com/4.x/windows/wazuh-agent-$wazuhVer-1.msi" `
        -OutFile $wazuhMsi -UseBasicParsing
} else { Write-Step "Wazuh MSI present — skipping." }

if (-not (Test-Path $zbxMsi)) {
    Write-Step "Downloading Zabbix agent2 ($zbxVer)..."
    Invoke-WebRequest -Uri "https://cdn.zabbix.com/zabbix/binaries/stable/$zbxMM/$zbxVer/zabbix_agent2-$zbxVer-windows-amd64-openssl.msi" `
        -OutFile $zbxMsi -UseBasicParsing
} else { Write-Step "Zabbix MSI present — skipping." }

if ($SkipMesh) {
    Write-Step "MeshCentral skipped (-SkipMesh). Bundle will contain Wazuh+Zabbix only."
} elseif (Test-Path $meshExe) {
    Write-Step "MeshCentral agent present — skipping."
} else {
    Write-Step "Downloading MeshCentral agent from your portal..."
    $meshUrl = "$($config.meshCentralUrl)/meshagents?id=4&meshid=$($config.meshId)"
    Invoke-WebRequest -Uri $meshUrl -OutFile $meshExe -UseBasicParsing
}

# ---------------------------------------------------------------------------
# 4. Build the bundle
# ---------------------------------------------------------------------------
$bundleWxs  = Join-Path $PSScriptRoot "wix\AaditechAgentBundle.wxs"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$outputExe  = Join-Path $OutputDir "Aaditech-Agent-Setup.exe"

Write-Step "Compiling bundle → Aaditech-Agent-Setup.exe ..."
$includeMesh = if ($SkipMesh) { "0" } else { "1" }
& wix build $bundleWxs -ext WixToolset.Bal.wixext -d "IncludeMesh=$includeMesh" -o $outputExe
if ($LASTEXITCODE -ne 0) { throw "wix build failed (exit $LASTEXITCODE). See messages above." }

Write-Host ""
Write-Host "DONE ✔  Bundle built: $outputExe" -ForegroundColor Green
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1. Upload Aaditech-Agent-Setup.exe to the portal download page."
Write-Host "  2. Endpoint install is silent by default; server values are passed"
Write-Host "     at deploy time (bal:Overridable), so the SAME .exe works in"
Write-Host "     localhost testing AND in the office environment — no rebuild."
Write-Host "  3. Example GPO command:"
Write-Host "     Aaditech-Agent-Setup.exe ManagerIp=10.0.0.10 ZabbixServerIp=10.0.0.10 MeshCentralUrl=https://portal.office.local:4433 WazuhEnrollKey=KEY"