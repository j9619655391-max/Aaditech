#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Aaditech Agent — Portal Command Poller (spec §3.5 wiring)
    Polls the portal for pending Category B commands (quarantine / restore /
    purge) and dispatches each to the matching endpoint script. This is the
    piece that closes the previously-documented gaps: portal-side
    approve/quarantine/restore/purge decisions now actually reach the
    endpoint instead of only updating a status field.

.DESCRIPTION
    Run on a schedule (Task Scheduler, every 1-5 minutes is reasonable —
    quarantine, restore and purge are not latency-sensitive operations). For
    each pending command:
      1. GET  /cleanup/agent/{EndpointId}/commands
      2. POST /cleanup/agent/commands/{id}/ack       (before running anything,
         so a crashed poller doesn't leave a command silently stuck)
      3. Dispatch to category-b-cleanup-execute.ps1 (quarantine),
         category-b-restore.ps1 (restore), or category-b-purge-execute.ps1
         (purge)
      4. POST /cleanup/agent/commands/{id}/complete  with success/result

.NOTES
    Auth: uses a per-endpoint service credential (bearer token), provisioned
    at agent install time — see docs/DEPLOYMENT.md. Never uses an engineer's
    personal session token.
#>

[CmdletBinding()]
param(
    [string]$PortalBaseUrl,          # e.g. https://portal.aaditech.local
    [string]$EndpointId,
    [string]$ServiceToken,
    [string]$ScriptDir = $PSScriptRoot,
    [string]$LogPath = "$env:ProgramData\Aaditech\logs\agent-command-poller.jsonl"
)

$ErrorActionPreference = "Stop"

# Prefer explicit params; otherwise fall back to the answer file that
# install-agent.bat wrote at install time (incl. the self-minted token), so
# the scheduled task needs no hand-typed arguments at all.
$answerFile = "$env:ProgramData\Aaditech\AADITECH_ENV.txt"
if (-not $PortalBaseUrl -or -not $EndpointId -or -not $ServiceToken) {
    if (-not (Test-Path $answerFile)) {
        Write-Error "No parameters provided and no $answerFile found. Run install-agent.bat first, or pass -PortalBaseUrl -EndpointId -ServiceToken."
        exit 1
    }
    $envMap = @{}
    Get-Content $answerFile | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') { $envMap[$matches[1]] = $matches[2] }
    }
    if (-not $PortalBaseUrl) { $PortalBaseUrl = $envMap["PORTAL_BASE_URL"] }
    if (-not $EndpointId)    { $EndpointId    = $envMap["ENDPOINT_ID"] }
    if (-not $ServiceToken)  { $ServiceToken  = $envMap["SERVICE_TOKEN"] }
}

if (-not $PortalBaseUrl -or -not $EndpointId -or -not $ServiceToken) {
    Write-Error "Missing required values. Got PortalBaseUrl='$PortalBaseUrl' EndpointId='$EndpointId' ServiceToken present=$(-not [string]::IsNullOrEmpty($ServiceToken))."
    exit 1
}

$headers = @{ Authorization = "Bearer $ServiceToken" }

function Write-AaditechLog {
    param([string]$CommandId, [string]$CommandType, [string]$Result)
    $entry = [PSCustomObject]@{
        timestamp    = (Get-Date).ToUniversalTime().ToString("o")
        agent        = "aaditech-command-poller"
        hostname     = $env:COMPUTERNAME
        command_id   = $CommandId
        command_type = $CommandType
        result       = $Result
    }
    $dir = Split-Path -Parent $LogPath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    ($entry | ConvertTo-Json -Compress) | Add-Content -Path $LogPath -Encoding utf8
}

function Complete-Command {
    param([string]$CommandId, [bool]$Success, [string]$Result)
    $body = @{ success = $Success; result = $Result } | ConvertTo-Json -Compress
    Invoke-RestMethod -Method Post -Uri "$PortalBaseUrl/cleanup/agent/commands/$CommandId/complete" `
        -Headers $headers -Body $body -ContentType "application/json" | Out-Null
}

try {
    $commands = Invoke-RestMethod -Method Get -Uri "$PortalBaseUrl/cleanup/agent/$EndpointId/commands" -Headers $headers
} catch {
    Write-AaditechLog -CommandId "-" -CommandType "-" -Result "poll_failed: $_"
    Write-Error "Failed to poll portal for commands: $_"
    exit 1
}

if (-not $commands -or $commands.Count -eq 0) {
    Write-Output "No pending commands."
    exit 0
}

foreach ($cmd in $commands) {
    $commandId = $cmd.command_id
    $commandType = $cmd.command_type
    $payload = $cmd.payload

    try {
        Invoke-RestMethod -Method Post -Uri "$PortalBaseUrl/cleanup/agent/commands/$commandId/ack" -Headers $headers | Out-Null
    } catch {
        Write-AaditechLog -CommandId $commandId -CommandType $commandType -Result "ack_failed: $_"
        continue  # skip execution if we couldn't even ack — avoid a silently duplicated action
    }

    switch ($commandType) {
        "quarantine" {
            try {
                $approvedPayload = @(@{
                    item_id         = $payload.item_id
                    path            = $payload.path
                    quarantine_path = $payload.quarantine_path
                }) | ConvertTo-Json -Depth 5 -Compress
                & "$ScriptDir\category-b-cleanup-execute.ps1" `
                    -ApprovedItemsJson $approvedPayload
                Write-AaditechLog -CommandId $commandId -CommandType $commandType -Result "dispatched_ok"
                Complete-Command -CommandId $commandId -Success $true -Result "quarantined"
            } catch {
                Write-AaditechLog -CommandId $commandId -CommandType $commandType -Result "dispatch_failed: $_"
                Complete-Command -CommandId $commandId -Success $false -Result "$_"
            }
        }
        "restore" {
            try {
                & "$ScriptDir\category-b-restore.ps1" `
                    -QuarantinePath $payload.quarantine_path `
                    -OriginalPath $payload.original_path `
                    -ItemId $payload.item_id
                Write-AaditechLog -CommandId $commandId -CommandType $commandType -Result "dispatched_ok"
                Complete-Command -CommandId $commandId -Success $true -Result "restored"
            } catch {
                Write-AaditechLog -CommandId $commandId -CommandType $commandType -Result "dispatch_failed: $_"
                Complete-Command -CommandId $commandId -Success $false -Result "$_"
            }
        }
        "purge" {
            try {
                & "$ScriptDir\category-b-purge-execute.ps1" `
                    -QuarantinePath $payload.quarantine_path `
                    -ItemId $payload.item_id
                Write-AaditechLog -CommandId $commandId -CommandType $commandType -Result "dispatched_ok"
                Complete-Command -CommandId $commandId -Success $true -Result "purged"
            } catch {
                Write-AaditechLog -CommandId $commandId -CommandType $commandType -Result "dispatch_failed: $_"
                Complete-Command -CommandId $commandId -Success $false -Result "$_"
            }
        }
        default {
            Write-AaditechLog -CommandId $commandId -CommandType $commandType -Result "unknown_command_type"
            Complete-Command -CommandId $commandId -Success $false -Result "unknown command_type: $commandType"
        }
    }
}
