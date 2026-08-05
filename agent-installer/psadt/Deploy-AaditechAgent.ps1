#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Aaditech Agent — PowerShell App Deployment Toolkit (PSADT) install script
    (spec §7.2 alternative to the WiX Burn bundle in ../wix/).

.DESCRIPTION
    Scripted alternative for teams that prefer PSADT over compiling a WiX
    bundle. Installs all three vendor agents silently and self-registers
    with no manual steps, matching the WiX bundle's behavior. Intended to
    be dropped into a standard PSADT "Toolkit" folder structure
    (Files\, SupportFiles\, AppDeployToolkit\) and invoked as
    Deploy-Application.ps1 is in a normal PSADT package — renamed here to
    make the Aaditech-specific logic obvious at a glance.

.NOTES
    Config values (manager IP, enrollment key, etc.) come from
    AgentConfig.json placed alongside this script at package time by the
    deployment automation — never hardcoded, matching the WiX bundle's
    Variable/MsiProperty approach.
#>

[CmdletBinding()]
param(
    [string]$ConfigPath = "$PSScriptRoot\..\AgentConfig.json",
    [string]$LogPath = "$env:ProgramData\Aaditech\logs\agent-install.jsonl"
)

$ErrorActionPreference = "Stop"

function Write-AaditechLog {
    param([string]$Component, [string]$Result, [string]$Detail = "")
    $entry = [PSCustomObject]@{
        timestamp = (Get-Date).ToUniversalTime().ToString("o")
        hostname  = $env:COMPUTERNAME
        component = $Component
        result    = $Result
        detail    = $Detail
    }
    $dir = Split-Path -Parent $LogPath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    ($entry | ConvertTo-Json -Compress) | Add-Content -Path $LogPath -Encoding utf8
}

if (-not (Test-Path $ConfigPath)) {
    Write-AaditechLog -Component "config" -Result "missing" -Detail $ConfigPath
    throw "AgentConfig.json not found at $ConfigPath — deployment automation must stage this alongside the script."
}
$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json

# Each install call is independent and logged individually — a failure on
# one vendor agent doesn't silently block the other two from being
# attempted, so a partial install is visible and diagnosable rather than
# an opaque single failure.
$results = @{}

function Install-VendorMsi {
    param([string]$Component, [string]$MsiPath, [string[]]$MsiArgs)

    if (-not (Test-Path $MsiPath)) {
        Write-AaditechLog -Component $Component -Result "msi_not_found" -Detail $MsiPath
        return $false
    }

    $argList = @("/i", "`"$MsiPath`"", "/qn", "/norestart") + $MsiArgs
    $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $argList -Wait -PassThru
    if ($proc.ExitCode -eq 0) {
        Write-AaditechLog -Component $Component -Result "installed"
        return $true
    } else {
        Write-AaditechLog -Component $Component -Result "failed" -Detail "msiexec exit code $($proc.ExitCode)"
        return $false
    }
}

$results.wazuh = Install-VendorMsi -Component "wazuh-agent" `
    -MsiPath "$PSScriptRoot\..\vendor\wazuh-agent.msi" `
    -MsiArgs @(
        "WAZUH_MANAGER=`"$($config.managerIp)`"",
        "WAZUH_REGISTRATION_SERVER=`"$($config.managerIp)`"",
        "WAZUH_REGISTRATION_PASSWORD=`"$($config.wazuhEnrollKey)`""
    )

$results.zabbix = Install-VendorMsi -Component "zabbix-agent" `
    -MsiPath "$PSScriptRoot\..\vendor\zabbix-agent.msi" `
    -MsiArgs @(
        "SERVER=`"$($config.zabbixServerIp)`"",
        "SERVERACTIVE=`"$($config.zabbixServerIp)`""
    )

$results.meshcentral = Install-VendorMsi -Component "meshcentral-agent" `
    -MsiPath "$PSScriptRoot\..\vendor\meshcentral-agent.msi" `
    -MsiArgs @("MESHURL=`"$($config.meshCentralUrl)`"")

$failed = $results.GetEnumerator() | Where-Object { -not $_.Value }
if ($failed) {
    Write-Output "Install completed with failures: $($failed.Name -join ', '). See $LogPath."
    exit 1
}

Write-Output "All three Aaditech Agent components installed successfully."
exit 0
