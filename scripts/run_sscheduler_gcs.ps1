# run_sscheduler_gcs.ps1
# Usage (PowerShell as user): .\scripts\run_sscheduler_gcs.ps1
# Prompts for 'r' to continue, elevates to add firewall rule if needed, then starts sscheduler\sgcs.py
param()

function Prompt-Confirm {
    param([string]$msg = "Press 'r' to continue, anything else to cancel:")
    $k = Read-Host -Prompt $msg
    if ($k -ne 'r') { Write-Host 'Cancelled.'; exit 1 }
}

Prompt-Confirm

# Ensure script runs from repo root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $scriptDir '..')

# Optionally add firewall rule (elevated)
$ruleName = 'secure-tunnel-gcs-48081'
$port = 48081

# Check if rule exists
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "Firewall rule $ruleName not found. Requesting elevation to add inbound rule for TCP port $port..."
    Start-Process -Verb RunAs -FilePath powershell -ArgumentList "-NoProfile -Command \"New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -LocalPort $port -Protocol TCP -Action Allow -Profile Any\""
    Start-Sleep -Seconds 1
} else {
    Write-Host "Firewall rule $ruleName already present."
}

# Start sscheduler sgcs in this user session and write to log
$logDir = Join-Path (Get-Location) 'logs\sscheduler\gcs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir "sgcs_$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

Write-Host "Starting sscheduler.sgcs (log: $logFile)"
python sscheduler\sgcs.py *> $logFile 2>&1 &
Write-Host "Started. Tail the log with: Get-Content -Wait $logFile"
