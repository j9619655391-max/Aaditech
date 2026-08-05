#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Aaditech Agent — Self-Healing Category B: RESTORE (spec §3.5)
    Moves a single quarantined item back to its original path, within the
    hold window. Triggered by the portal's
    POST /cleanup/items/{report_id}/{item_id}/restore endpoint, which
    audit-logs the restore server-side (app/audit.py,
    AuditAction.CATEGORY_B_RESTORE) — this script performs the matching
    filesystem action on the endpoint.

.NOTES
    Invoked by agent-command-poller.ps1, which polls
    GET /cleanup/agent/{endpoint_id}/commands, acks the command, runs this
    script with the command's quarantine_path/original_path, and reports
    success/failure back to POST /cleanup/agent/commands/{id}/complete.
    See app/agent_commands.py for the portal-side queue this reads from.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$QuarantinePath,
    [Parameter(Mandatory = $true)][string]$OriginalPath,
    [string]$ItemId,
    [string]$LogPath = "$env:ProgramData\Aaditech\logs\category-b-restore.jsonl"
)

$ErrorActionPreference = "Stop"

function Write-AaditechLog {
    param([string]$Result)
    $entry = [PSCustomObject]@{
        timestamp        = (Get-Date).ToUniversalTime().ToString("o")
        agent             = "aaditech-category-b-restore"
        hostname          = $env:COMPUTERNAME
        item_id           = $ItemId
        quarantine_path   = $QuarantinePath
        original_path     = $OriginalPath
        result            = $Result
    }
    $dir = Split-Path -Parent $LogPath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    ($entry | ConvertTo-Json -Compress) | Add-Content -Path $LogPath -Encoding utf8
}

if (-not (Test-Path $QuarantinePath)) {
    Write-AaditechLog -Result "quarantine_source_missing"
    Write-Error "Quarantined item not found at $QuarantinePath — it may have already been purged."
    exit 1
}

try {
    $destDir = Split-Path -Parent $OriginalPath
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    Move-Item -Path $QuarantinePath -Destination $OriginalPath -Force
    Write-AaditechLog -Result "restored"
    Write-Output "Restored $QuarantinePath -> $OriginalPath"
    exit 0
} catch {
    Write-AaditechLog -Result "failed: $_"
    Write-Error "Restore failed: $_"
    exit 1
}
