#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Aaditech Agent — Self-Healing Category B: EXECUTE (spec §3.5)
    Moves ONLY items explicitly approved via the Aaditech Portal
    ("Approve & Execute") into quarantine. NEVER permanently deletes
    anything itself — permanent purge happens later, automatically, via
    the ILM job once the quarantine hold window expires (§3.3).

.DESCRIPTION
    Called with an -ApprovedItemsJson payload matching the shape returned
    by POST /cleanup/scan-reports/{id}/approve on the portal backend:
    a list of {item_id, path, quarantine_path, expires_at, hold_type}.
    This script is the ONLY place on the endpoint where a Category B item
    actually moves — the scan script (category-b-cleanup-scan.ps1) never
    touches anything, it only reports.

.NOTES
    Every move is logged locally and forwarded to central Wazuh storage
    (§7.4), matching the audit trail already recorded on the portal side
    when the approval was made (app/audit.py, AuditAction.CATEGORY_B_APPROVE_EXECUTE).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ApprovedItemsJson,   # JSON array: [{item_id, path, quarantine_path, expires_at, hold_type}, ...]

    [string]$LogPath = "$env:ProgramData\Aaditech\logs\category-b-execute.jsonl"
)

$ErrorActionPreference = "Stop"

function Write-AaditechLog {
    param([string]$Action, [string]$Detail, [string]$Result)
    $entry = [PSCustomObject]@{
        timestamp = (Get-Date).ToUniversalTime().ToString("o")
        agent     = "aaditech-category-b-execute"
        hostname  = $env:COMPUTERNAME
        action    = $Action
        detail    = $Detail
        result    = $Result
    }
    $dir = Split-Path -Parent $LogPath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    ($entry | ConvertTo-Json -Compress) | Add-Content -Path $LogPath -Encoding utf8
}

function Move-ItemToQuarantine {
    param([string]$SourcePath, [string]$QuarantinePath, [string]$ItemId)

    if (-not (Test-Path $SourcePath)) {
        Write-AaditechLog -Action "quarantine_move" -Detail "$ItemId : $SourcePath" -Result "source_missing_skipped"
        return
    }

    $destDir = Split-Path -Parent $QuarantinePath
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }

    try {
        # Move (not copy+delete) so nothing is ever duplicated or briefly
        # unaccounted for between source and quarantine.
        Move-Item -Path $SourcePath -Destination $QuarantinePath -Force
        Write-AaditechLog -Action "quarantine_move" -Detail "$ItemId : $SourcePath -> $QuarantinePath" -Result "moved"
    } catch {
        Write-AaditechLog -Action "quarantine_move" -Detail "$ItemId : $SourcePath" -Result "failed: $_"
        throw
    }
}

# --- Main ---
$approvedItems = $ApprovedItemsJson | ConvertFrom-Json

if (-not $approvedItems -or $approvedItems.Count -eq 0) {
    Write-Output "No approved items provided — nothing to do."
    exit 0
}

$successCount = 0
$failCount = 0

foreach ($item in $approvedItems) {
    try {
        Move-ItemToQuarantine -SourcePath $item.path -QuarantinePath $item.quarantine_path -ItemId $item.item_id
        $successCount++
    } catch {
        $failCount++
    }
}

Write-Output "Quarantine execution complete: $successCount moved, $failCount failed. See $LogPath for details."

if ($failCount -gt 0) { exit 1 } else { exit 0 }
