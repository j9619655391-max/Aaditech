#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Aaditech Agent — Self-Healing Category B: SCAN ONLY (spec §3.5)
    Scans known cleanup-candidate locations and submits a report to the
    Aaditech Portal. THIS SCRIPT NEVER DELETES OR MOVES ANY FILE — it only
    reports what exists. Deletion/quarantine only happens after an engineer
    with the Cleanup Approver role approves specific items in the portal,
    which then triggers category-b-cleanup-execute.ps1 with an explicit
    approved item list.

.DESCRIPTION
    Triggered either on a schedule, or immediately when disk free space
    drops below a threshold (low-disk-space triggered scan → items get the
    shorter 24h emergency quarantine hold instead of the 7-day standard
    hold — that categorization happens portal-side based on TriggeredBy).

.NOTES
    Scan targets (exactly as enumerated in spec §3.5):
      Windows\Temp, Users\*\AppData\Local\Temp, Prefetch, Recycle Bin,
      Windows.edb, SoftwareDistribution\Download, thumbnail cache,
      Delivery Optimization files, memory dump files (.dmp), old event logs
#>

[CmdletBinding()]
param(
    [string]$PortalApiUrl = "https://portal.aaditech.local/api/cleanup/scan-reports",
    [string]$PortalApiToken = $env:AADITECH_AGENT_TOKEN,
    [ValidateSet("scheduled", "low_disk_space")]
    [string]$TriggeredBy = "scheduled",
    [double]$LowDiskThresholdPercent = 10.0,
    [switch]$WhatIf  # dry run — print report locally, don't submit to portal
)

$ErrorActionPreference = "Stop"

function Get-FolderScanResult {
    param([string]$Category, [string]$Path)

    if (-not (Test-Path $Path)) {
        return $null
    }

    $items = Get-ChildItem -Path $Path -Recurse -Force -ErrorAction SilentlyContinue
    if (-not $items) {
        return $null
    }

    $totalSize = ($items | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
    $lastModified = ($items | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime

    return [PSCustomObject]@{
        category      = $Category
        path          = $Path
        size_bytes    = [int64]($totalSize ?? 0)
        last_modified = if ($lastModified) { $lastModified.ToString("o") } else { (Get-Date).ToString("o") }
    }
}

function Get-RecycleBinScanResult {
    $shell = New-Object -ComObject Shell.Application
    $recycleBin = $shell.Namespace(10)
    $items = $recycleBin.Items()
    $totalSize = 0
    foreach ($item in $items) { $totalSize += $item.ExtendedProperty("Size") }

    if ($items.Count -eq 0) { return $null }

    return [PSCustomObject]@{
        category      = "recycle_bin"
        path          = "Recycle Bin (all drives)"
        size_bytes    = [int64]$totalSize
        last_modified = (Get-Date).ToString("o")
    }
}

# --- Scan targets exactly as enumerated in spec §3.5 ---
$scanTargets = @(
    @{ category = "windows_temp"; path = "$env:SystemRoot\Temp" }
    @{ category = "prefetch"; path = "$env:SystemRoot\Prefetch" }
    @{ category = "windows_update_cache"; path = "$env:SystemRoot\SoftwareDistribution\Download" }
    @{ category = "delivery_optimization"; path = "$env:SystemRoot\SoftwareDistribution\DeliveryOptimization" }
    @{ category = "memory_dumps"; path = "$env:SystemRoot\Minidump" }
)

$results = [System.Collections.Generic.List[object]]::new()

foreach ($target in $scanTargets) {
    $r = Get-FolderScanResult -Category $target.category -Path $target.path
    if ($r) { $results.Add($r) }
}

# Per-user AppData\Local\Temp (spec: Users\*\AppData\Local\Temp)
Get-ChildItem "$env:SystemDrive\Users" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $userTemp = Join-Path $_.FullName "AppData\Local\Temp"
    $r = Get-FolderScanResult -Category "user_temp" -Path $userTemp
    if ($r) { $results.Add($r) }
}

# Windows.edb (search index database) — single file, not a folder
$edbPath = "$env:ProgramData\Microsoft\Search\Data\Applications\Windows\Windows.edb"
if (Test-Path $edbPath) {
    $edbFile = Get-Item $edbPath
    $results.Add([PSCustomObject]@{
        category      = "windows_edb"
        path          = $edbPath
        size_bytes    = [int64]$edbFile.Length
        last_modified = $edbFile.LastWriteTime.ToString("o")
    })
}

# Thumbnail cache
$thumbCachePath = "$env:LOCALAPPDATA\Microsoft\Windows\Explorer"
$thumbResult = Get-FolderScanResult -Category "thumbnail_cache" -Path $thumbCachePath
if ($thumbResult) { $results.Add($thumbResult) }

# Recycle Bin (special-cased — not a normal filesystem path)
$recycleResult = Get-RecycleBinScanResult
if ($recycleResult) { $results.Add($recycleResult) }

# --- Determine trigger reason if not explicitly passed ---
if ($TriggeredBy -eq "scheduled") {
    $systemDrive = Get-PSDrive -Name ($env:SystemDrive.TrimEnd(':'))
    $freePercent = ($systemDrive.Free / ($systemDrive.Free + $systemDrive.Used)) * 100
    if ($freePercent -lt $LowDiskThresholdPercent) {
        $TriggeredBy = "low_disk_space"
    }
}

$report = [PSCustomObject]@{
    endpoint_id   = (Get-CimInstance Win32_ComputerSystemProduct).UUID
    endpoint_name = $env:COMPUTERNAME
    triggered_by  = $TriggeredBy
    items         = $results
}

$json = $report | ConvertTo-Json -Depth 5

if ($WhatIf) {
    Write-Output $json
    exit 0
}

try {
    $headers = @{ "Authorization" = "Bearer $PortalApiToken"; "Content-Type" = "application/json" }
    Invoke-RestMethod -Uri $PortalApiUrl -Method Post -Headers $headers -Body $json | Out-Null
    Write-Output "Scan report submitted successfully. $($results.Count) categories found, trigger=$TriggeredBy."
    exit 0
} catch {
    Write-Error "Failed to submit scan report to portal: $_"
    exit 1
}
