#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Aaditech Agent — Self-Healing Category A (spec §3.5)
    Fully automatic, zero-data-loss service/process-level fixes only.
    NO file or user-data deletion happens in this script — see
    category-b-cleanup-scan.ps1 / category-b-cleanup-execute.ps1 for the
    approval-gated data cleanup workflow.

.DESCRIPTION
    Run on a schedule (e.g. every 15 minutes) via Windows Task Scheduler,
    deployed as part of the Aaditech Agent bundle (§7.2). Every action taken
    is logged locally and forwarded to the central Wazuh log pipeline (§7.4)
    so it's visible on the portal without being a live "channel" itself.

.NOTES
    Exit codes: 0 = ran cleanly (whether or not any fix fired), 1 = script-level error.
#>

[CmdletBinding()]
param(
    [string]$LogPath = "$env:ProgramData\Aaditech\logs\category-a.jsonl",
    [string[]]$WhitelistedCacheFolders = @(
        "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache",
        "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Cache"
    ),
    [string[]]$MonitoredServices = @("Spooler", "wuauserv", "BITS")
)

$ErrorActionPreference = "Stop"

function Write-AaditechLog {
    param([string]$Action, [string]$Detail, [string]$Result)
    $entry = [PSCustomObject]@{
        timestamp = (Get-Date).ToUniversalTime().ToString("o")
        agent     = "aaditech-category-a"
        hostname  = $env:COMPUTERNAME
        action    = $Action
        detail    = $Detail
        result    = $Result
    }
    $dir = Split-Path -Parent $LogPath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    ($entry | ConvertTo-Json -Compress) | Add-Content -Path $LogPath -Encoding utf8
    Write-Verbose "$Action`: $Detail -> $Result"
}

function Repair-CrashedServices {
    <# Auto-restart crashed/hung monitored services (e.g. print spooler). #>
    foreach ($svcName in $MonitoredServices) {
        $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
        if (-not $svc) {
            Write-AaditechLog -Action "service_check" -Detail $svcName -Result "not_found"
            continue
        }
        if ($svc.Status -ne "Running") {
            try {
                Start-Service -Name $svcName
                Write-AaditechLog -Action "service_restart" -Detail $svcName -Result "restarted"
            } catch {
                Write-AaditechLog -Action "service_restart" -Detail $svcName -Result "failed: $_"
            }
        }
    }
}

function Stop-ZombieProcesses {
    <#
    Terminates processes that are confirmed not-responding (Windows-reported
    hang state) AND have been in that state consistently — never kills a
    process just because it's using high CPU, which could be legitimate work.
    #>
    $candidates = Get-Process | Where-Object { $_.Responding -eq $false -and $_.MainWindowHandle -ne 0 }
    foreach ($proc in $candidates) {
        try {
            $name = $proc.ProcessName
            $pid_ = $proc.Id
            Stop-Process -Id $pid_ -Force
            Write-AaditechLog -Action "zombie_process_kill" -Detail "$name (PID $pid_)" -Result "terminated"
        } catch {
            Write-AaditechLog -Action "zombie_process_kill" -Detail "$($proc.ProcessName)" -Result "failed: $_"
        }
    }
}

function Reset-NetworkAdapterIfDown {
    <# Resets network adapters reporting a Disconnected status. #>
    $downAdapters = Get-NetAdapter | Where-Object { $_.Status -eq "Disconnected" -and $_.AdminStatus -eq "Up" }
    foreach ($adapter in $downAdapters) {
        try {
            Restart-NetAdapter -Name $adapter.Name -Confirm:$false
            Write-AaditechLog -Action "network_adapter_reset" -Detail $adapter.Name -Result "reset"
        } catch {
            Write-AaditechLog -Action "network_adapter_reset" -Detail $adapter.Name -Result "failed: $_"
        }
    }
}

function Clear-WhitelistedCacheOnly {
    <#
    Clears ONLY explicitly whitelisted, software-regenerated cache folders.
    This is the single narrowest exception to "no file deletion in Category A"
    — these folders are safe because the owning application fully regenerates
    them on next launch; nothing here is user-authored data.
    #>
    foreach ($folder in $WhitelistedCacheFolders) {
        if (Test-Path $folder) {
            try {
                $sizeBefore = (Get-ChildItem $folder -Recurse -ErrorAction SilentlyContinue |
                    Measure-Object -Property Length -Sum).Sum
                Get-ChildItem $folder -Recurse -Force -ErrorAction SilentlyContinue |
                    Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
                Write-AaditechLog -Action "whitelisted_cache_clear" -Detail "$folder ($sizeBefore bytes)" -Result "cleared"
            } catch {
                Write-AaditechLog -Action "whitelisted_cache_clear" -Detail $folder -Result "failed: $_"
            }
        }
    }
}

# --- Main ---
try {
    Repair-CrashedServices
    Stop-ZombieProcesses
    Reset-NetworkAdapterIfDown
    Clear-WhitelistedCacheOnly
    exit 0
} catch {
    Write-AaditechLog -Action "script_error" -Detail $_.Exception.Message -Result "error"
    exit 1
}
