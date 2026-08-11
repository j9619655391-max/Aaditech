#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Aaditech Agent — ONE-CLICK installer for a Windows endpoint (spec §7.2).
    This is the only script you run on a Windows machine. It downloads all
    three vendor agents automatically and installs them silently — no
    separate download step, no running multiple scripts in sequence.

.DESCRIPTION
    Reads AgentConfig.json (same folder), then:
      1. Downloads the Wazuh agent MSI directly from packages.wazuh.com
         (real, versioned, publicly downloadable — no login needed)
      2. Downloads the Zabbix agent 2 MSI directly from cdn.zabbix.com
         (same — real, versioned, publicly downloadable)
      3. Downloads the MeshCentral agent from YOUR OWN Aaditech Portal's
         MeshCentral instance — this one is NOT a public vendor download.
         MeshCentral agents are generated per-server and tied to a specific
         device group (mesh ID); they only exist once your own portal is
         deployed and a device group has been created in it. That's a
         property of how MeshCentral works, not a gap in this script.
      4. Installs all three silently (msiexec /qn), no manual clicking.

.NOTES
    Run once per Windows endpoint (or push via GPO/Intune as a single
    scheduled task — see docs/DEPLOYMENT.md "Agent rollout to the fleet").
    For a mass rollout, use agent-installer/wix/AaditechAgentBundle.wxs
    instead — this script is the fast path for a single machine or a
    small pilot ring.
#>

[CmdletBinding()]
param(
    [string]$ConfigPath = "$PSScriptRoot\AgentConfig.json",
    [string]$WorkDir = "$env:TEMP\aaditech-agent-install",
    [string]$LogPath = "$env:ProgramData\Aaditech\logs\one-click-install.jsonl"
)

$ErrorActionPreference = "Stop"

function Write-AaditechLog {
    param([string]$Step, [string]$Result, [string]$Detail = "")
    $entry = [PSCustomObject]@{
        timestamp = (Get-Date).ToUniversalTime().ToString("o")
        hostname  = $env:COMPUTERNAME
        step      = $Step
        result    = $Result
        detail    = $Detail
    }
    $dir = Split-Path -Parent $LogPath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    ($entry | ConvertTo-Json -Compress) | Add-Content -Path $LogPath -Encoding utf8
    Write-Output "[$Step] $Result $(if ($Detail) { "- $Detail" })"
}

# --- 0. Config ---
if (-not (Test-Path $ConfigPath)) {
    Write-AaditechLog -Step "config" -Result "missing" -Detail $ConfigPath
    throw @"
AgentConfig.json not found at $ConfigPath.
Copy AgentConfig.sample.json to AgentConfig.json and fill in your values
first — this is the ONE piece of information that genuinely can't be
auto-downloaded, since it's specific to YOUR deployment (your manager IP,
your enrollment key, your portal's mesh ID). Everything else this script
does automatically.
"@
}
$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null

# --- 1. Download Wazuh agent MSI ---
$wazuhVersion = $config.wazuhAgentVersion   # e.g. "4.9.0"
$wazuhUrl = "https://packages.wazuh.com/4.x/windows/wazuh-agent-$wazuhVersion-1.msi"
$wazuhMsi = "$WorkDir\wazuh-agent-$wazuhVersion-1.msi"
try {
    Invoke-WebRequest -Uri $wazuhUrl -OutFile $wazuhMsi -UseBasicParsing
    Write-AaditechLog -Step "download_wazuh" -Result "ok" -Detail $wazuhUrl
} catch {
    Write-AaditechLog -Step "download_wazuh" -Result "failed" -Detail "$_"
    throw "Failed to download Wazuh agent from $wazuhUrl — check wazuhAgentVersion in AgentConfig.json matches a real published version."
}

# --- 2. Download Zabbix agent 2 MSI ---
$zbxVersion = $config.zabbixAgentVersion    # e.g. "6.4.20"
$zbxMajorMinor = ($zbxVersion -split '\.')[0..1] -join '.'
$zbxUrl = "https://cdn.zabbix.com/zabbix/binaries/stable/$zbxMajorMinor/$zbxVersion/zabbix_agent2-$zbxVersion-windows-amd64-openssl.msi"
$zbxMsi = "$WorkDir\zabbix_agent2-$zbxVersion-windows-amd64-openssl.msi"
try {
    Invoke-WebRequest -Uri $zbxUrl -OutFile $zbxMsi -UseBasicParsing
    Write-AaditechLog -Step "download_zabbix" -Result "ok" -Detail $zbxUrl
} catch {
    Write-AaditechLog -Step "download_zabbix" -Result "failed" -Detail "$_"
    throw "Failed to download Zabbix agent from $zbxUrl — check zabbixAgentVersion in AgentConfig.json matches a real published version."
}

# --- 3. Download the MeshCentral agent from YOUR OWN portal ---
# Not a public vendor URL by design (see .DESCRIPTION) — requires your
# portal to already be up and a device group (mesh) to already exist there.
$meshUrl = "$($config.meshCentralUrl)/meshagents?id=4&meshid=$($config.meshId)"
$meshExe = "$WorkDir\aaditech-mesh-agent.exe"
# NOTE: uses the portal's HTTPS cert (mkcert-issued, §7.6). This endpoint
# must already trust the mkcert CA (setup-certs.sh prints the one-line
# `mkcert -install` command for team/endpoint machines) — deliberately NOT
# bypassing certificate validation here, since -SkipCertificateCheck only
# exists on PowerShell 7+ and most managed endpoints run Windows PowerShell
# 5.1 by default; trusting the CA once is the correct fix either way.
try {
    Invoke-WebRequest -Uri $meshUrl -OutFile $meshExe -UseBasicParsing
    Write-AaditechLog -Step "download_meshcentral" -Result "ok" -Detail $meshUrl
} catch {
    Write-AaditechLog -Step "download_meshcentral" -Result "failed" -Detail "$_"
    throw "Failed to download the MeshCentral agent from $meshUrl — confirm the portal is up, meshCentralUrl/meshId in AgentConfig.json are correct, a device group exists in MeshCentral, and this machine trusts the mkcert CA (see infra/setup-certs.sh output for the one-line command)."
}

# --- 4. Install all three silently ---
function Install-Msi {
    param([string]$Component, [string]$MsiPath, [string[]]$Properties)
    $argList = @("/i", "`"$MsiPath`"", "/qn", "/norestart") + $Properties
    $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $argList -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        Write-AaditechLog -Step "install_$Component" -Result "failed" -Detail "exit code $($proc.ExitCode)"
        throw "$Component install failed (msiexec exit code $($proc.ExitCode))"
    }
    Write-AaditechLog -Step "install_$Component" -Result "ok"
}

Install-Msi -Component "wazuh" -MsiPath $wazuhMsi -Properties @(
    "WAZUH_MANAGER=`"$($config.managerIp)`"",
    "WAZUH_REGISTRATION_SERVER=`"$($config.managerIp)`"",
    "WAZUH_REGISTRATION_PASSWORD=`"$($config.wazuhEnrollKey)`""
)

Install-Msi -Component "zabbix" -MsiPath $zbxMsi -Properties @(
    "SERVER=`"$($config.zabbixServerIp)`"",
    "SERVERACTIVE=`"$($config.zabbixServerIp)`""
)

# MeshCentral's generated .exe is a self-installer, not an MSI — different
# invocation (silent install flag, per MeshAgent convention).
try {
    Start-Process -FilePath $meshExe -ArgumentList "-fullinstall" -Wait
    Write-AaditechLog -Step "install_meshcentral" -Result "ok"
} catch {
    Write-AaditechLog -Step "install_meshcentral" -Result "failed" -Detail "$_"
    throw "MeshCentral agent install failed: $_"
}

Write-Output ""
Write-Output "All three Aaditech Agent components installed. Log: $LogPath"
Write-Output "Verify in the portal's Agent Health dashboard within a few minutes."
