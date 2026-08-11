param(
  # Optional: opens a separate window that SSHes to the drone and starts sdrone_bench
  [string]$DroneSshTarget = "",
  [string]$DroneRepoPath = "~/secure-tunnel",
  [string]$DroneActivate = "source ~/cenv/bin/activate",
  [int]$MaxSuites = 1,
  [int]$IntervalSec = 10,

  # Python environment
  [string]$CondaEnv = "oqs-dev",

  # Metrics waiting/validation
  [int]$WaitTimeoutSec = 600,
  [string]$ComprehensiveDir = "logs\\benchmarks\\comprehensive",

  # Process cleanup
  [switch]$SkipKill,
  [switch]$SkipLogRotate
)

$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
  # $MyInvocation is function-scoped; use script-scoped path vars instead.
  $scriptDir = $PSScriptRoot
  if (-not $scriptDir) {
    if ($PSCommandPath) {
      $scriptDir = Split-Path -Parent $PSCommandPath
    } else {
      throw "Cannot determine script directory (PSScriptRoot/PSCommandPath missing)."
    }
  }
  return (Resolve-Path (Join-Path $scriptDir '..')).Path
}

function Rotate-Logs([string]$repoRoot) {
  $logsDir = Join-Path $repoRoot 'logs'
  if (-not (Test-Path $logsDir)) { return }

  $legacyDir = Join-Path $logsDir 'legacy'
  if (-not (Test-Path $legacyDir)) { New-Item -ItemType Directory -Path $legacyDir | Out-Null }

  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $dest = Join-Path $legacyDir $stamp
  New-Item -ItemType Directory -Path $dest | Out-Null

  Get-ChildItem $logsDir -Force | Where-Object {
    $_.Name -ne 'legacy'
  } | ForEach-Object {
    try {
      Move-Item -Force -Path $_.FullName -Destination $dest
    } catch {
      Write-Host "WARN: failed to move $($_.FullName): $($_.Exception.Message)"
    }
  }

  # Recreate commonly used dirs
  New-Item -ItemType Directory -Path (Join-Path $logsDir 'sscheduler\\gcs') -Force | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $logsDir 'benchmarks\\comprehensive') -Force | Out-Null
}

function Kill-RunawayProcs {
  $names = @(
    'python', 'python3',
    'mavproxy', 'MAVProxy',
    'secure-tunnel',
    'oqs-tunnel'
  )

  foreach ($n in $names) {
    Get-Process -Name $n -ErrorAction SilentlyContinue | ForEach-Object {
      try {
        Stop-Process -Id $_.Id -Force
      } catch {
        Write-Host "WARN: couldn't stop $n pid=$($_.Id): $($_.Exception.Message)"
      }
    }
  }
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

if (-not $SkipLogRotate) {
  Write-Host "Rotating logs -> logs\\legacy\\<timestamp>"
  Rotate-Logs -repoRoot $repoRoot
}

if (-not $SkipKill) {
  Write-Host "Killing python/mavproxy processes (Windows side)"
  Kill-RunawayProcs
}

# Prefer running via conda env (works even if not activated)
$condaExe = (Get-Command conda -ErrorAction SilentlyContinue).Source
if (-not $condaExe) {
  throw "conda not found in PATH. Open an 'Anaconda Prompt' or add conda to PATH."
}

$pythonPrefix = "conda run -n $CondaEnv python"

# Start GCS scheduler in a new PowerShell window
$sgcsCmd = "Set-Location -LiteralPath '$repoRoot'; $pythonPrefix -m sscheduler.sgcs"
Write-Host "Starting GCS: $sgcsCmd"
Start-Process -FilePath powershell -ArgumentList @('-NoExit','-NoProfile','-Command', $sgcsCmd)

# Optionally start drone bench via SSH in a new window
if ($DroneSshTarget -and $DroneSshTarget.Trim().Length -gt 0) {
  $remoteCmd = "cd $DroneRepoPath; $DroneActivate; python -m sscheduler.sdrone_bench --interval $IntervalSec --max-suites $MaxSuites"
  # PowerShell escaping: use backtick to embed double quotes inside a double-quoted string
  $sshCmd = "ssh $DroneSshTarget `"$remoteCmd`""
  Write-Host "Starting DRONE over SSH: $sshCmd"
  Start-Process -FilePath powershell -ArgumentList @('-NoExit','-NoProfile','-Command', $sshCmd)
} else {
  Write-Host "NOTE: Drone bench not auto-started (pass -DroneSshTarget to enable)."
}

# Wait until we have both drone+gcs A–R metrics files
$waitScript = Join-Path $repoRoot 'tools\\wait_for_comprehensive_metrics.py'
$watchDir = Join-Path $repoRoot $ComprehensiveDir
Write-Host "Waiting for comprehensive metrics in: $watchDir (timeout=${WaitTimeoutSec}s)"
& $condaExe run -n $CondaEnv python $waitScript --dir $watchDir --timeout $WaitTimeoutSec
