#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Aaditech Agent — Self-Healing Category B: PURGE EXECUTE (spec §3.5)
    Permanently deletes a single item from quarantine after its hold window
    has expired. This is the ONLY script that performs an unrecoverable
    delete on the endpoint — everything upstream of this (scan, execute,
    the portal's ILM-driven purge-expired check) only ever moves items
    into quarantine or decides which are past their window.

.DESCRIPTION
    Invoked by agent-command-poller.ps1 for a PURGE command, which the
    portal enqueues from POST /cleanup/purge-expired (the ILM cron job,
    §3.3, §7.4) — never called directly against a live/original path.

.NOTES
    A missing quarantine source is logged, not treated as failure — the
    item may already have been purged by a prior run (idempotent).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$QuarantinePath,
    [string]$ItemId,
    [string]$LogPath = "$env:ProgramData\Aaditech\logs\category-b-purge.jsonl"
)

$ErrorActionPreference = "Stop"

function Write-AaditechLog {
    param([string]$Result)
    $entry = [PSCustomObject]@{
        timestamp       = (Get-Date).ToUniversalTime().ToString("o")
        agent           = "aaditech-category-b-purge"
        hostname        = $env:COMPUTERNAME
        item_id         = $ItemId
        quarantine_path = $QuarantinePath
        result          = $Result
    }
    $dir = Split-Path -Parent $LogPath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    ($entry | ConvertTo-Json -Compress) | Add-Content -Path $LogPath -Encoding utf8
}

if (-not (Test-Path $QuarantinePath)) {
    Write-AaditechLog -Result "already_absent"
    Write-Output "Nothing to purge at $QuarantinePath (already gone) — treating as success."
    exit 0
}

try {
    Remove-Item -Path $QuarantinePath -Recurse -Force
    Write-AaditechLog -Result "purged"
    Write-Output "Permanently purged $QuarantinePath"
    exit 0
} catch {
    Write-AaditechLog -Result "failed: $_"
    Write-Error "Purge failed: $_"
    exit 1
}
