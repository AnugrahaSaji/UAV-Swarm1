#!/usr/bin/env pwsh
<#
.SYNOPSIS
    5-Phase DDoS × PQC Impact Benchmark
    ====================================
    Measures how DDoS detection affects PQC tunnel performance and vice versa.

    Phase A : Baseline       — no PQC tunnel, no detector
    Phase B1: DDoS-only XGB  — no PQC tunnel, XGBoost running
    Phase B2: DDoS-only TST  — no PQC tunnel, TransformerIDS running
    Phase C : PQC-only       — full 72-suite tunnel, no detector
    Phase D : PQC + XGBoost  — full 72-suite tunnel with XGBoost
    Phase E : PQC + TST      — full 72-suite tunnel with TransformerIDS

    Phases A–B measure raw system overhead (CPU, temp, power, RAM)
    using collect_overhead.py on the Pi4.
    Phases C–E use the existing sdrone_bench/sgcs_bench infrastructure
    to produce comprehensive per-suite JSONs with handshake time,
    throughput, latency, power, etc.

    Final output: a comparison JSON combining all phases.

.PARAMETER OverheadDuration
    Seconds for each overhead-only phase (A, B1, B2).  Default: 120
.PARAMETER IntervalSec
    Seconds per PQC suite (Phases C–E).  Default: 10
.PARAMETER MaxSuites
    Limit number of suites for PQC phases (0 = all 72).  Default: 0
.PARAMETER SkipOverhead
    Skip Phases A, B1, B2 (overhead-only)
.PARAMETER SkipPqcOnly
    Skip Phase C (PQC without detector)
.PARAMETER SkipXgb
    Skip Phases B1 and D (XGBoost phases)
.PARAMETER SkipTst
    Skip Phases B2 and E (TST phases)
.PARAMETER DroneSsh
    SSH target for the Pi4.  Default: dev@100.101.93.23
.PARAMETER CondaEnv
    Conda env for GCS Python.  Default: oqs-dev
.PARAMETER RunTag
    Tag for output directory.  Default: current date
.PARAMETER FilterAead
    Optional: only benchmark suites matching this AEAD
.PARAMETER FilterKem
    Optional: only benchmark suites matching this KEM
#>
param(
    [int]$OverheadDuration = 120,
    [int]$IntervalSec      = 10,
    [int]$MaxSuites        = 0,
    [switch]$SkipOverhead,
    [switch]$SkipPqcOnly,
    [switch]$SkipXgb,
    [switch]$SkipTst,
    [string]$DroneSsh      = "dev@100.101.93.23",
    [string]$CondaEnv      = "oqs-dev",
    [string]$RunTag        = $(Get-Date -Format "yyyyMMdd_HHmm"),
    [string]$FilterAead    = "",
    [string]$FilterKem     = ""
)

$ErrorActionPreference = 'Continue'

# ── Paths ────────────────────────────────────────────────────────────
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $RepoRoot

$OutDir        = Join-Path $RepoRoot "logs\benchmarks\ddos_pqc_impact\$RunTag"
$DroneRepo     = "~/secure-tunnel"
$DetectorPython = "/home/dev/nenv/bin/python"
$DronePython   = "/home/dev/cenv/bin/python"
$OverheadScript = "benchmarks/ddos_pqc_impact/collect_overhead.py"
$E2EScript     = Join-Path $RepoRoot "scripts\run_e2e_benchmark.ps1"

# ── Banner ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "  5-PHASE DDoS x PQC IMPACT BENCHMARK" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "  Run tag           : $RunTag"
Write-Host "  Overhead duration : ${OverheadDuration}s per phase"
Write-Host "  PQC interval      : ${IntervalSec}s per suite"
Write-Host "  PQC suites        : $(if ($MaxSuites -eq 0) { 'ALL (72)' } else { $MaxSuites })"
Write-Host "  Drone SSH         : $DroneSsh"
Write-Host "  Output            : $OutDir"
Write-Host "  Phases            : $(if (!$SkipOverhead) {'A B1 B2 '})$(if (!$SkipPqcOnly) {'C '})$(if (!$SkipXgb) {'D '})$(if (!$SkipTst) {'E'})"
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""

# ── Helpers ──────────────────────────────────────────────────────────

function Test-SshOk {
    $result = ssh -o ConnectTimeout=10 $DroneSsh "echo OK" 2>&1
    return ($result -match "OK")
}

function Kill-AllBenchProcesses {
    Write-Host "  Cleaning up benchmark processes..." -NoNewline
    # Drone side
    $patterns = @('sscheduler.sdrone_bench', 'sscheduler.sgcs_bench', 'core.run_proxy',
                  'MAVProxy.mavproxy', 'ddos/xgb', 'ddos/tst', 'ddos/lgbm', 'ddos/rf',
                  'collect_overhead')
    foreach ($p in $patterns) {
        ssh -o ConnectTimeout=10 $DroneSsh "sudo pkill -f '$p' 2>/dev/null" 2>&1 | Out-Null
    }
    # GCS side — targeted
    Get-Process -Name "python","python3" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and ($_.CommandLine -match 'sgcs_bench|sdrone_bench|run_proxy|sscheduler')
    } | ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} }
    Get-Process -Name "mavproxy" -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force } catch {}
    }
    Start-Sleep -Seconds 2
    Write-Host " done"
}

function Run-OverheadPhase([string]$Label, [string]$Detector) {
    <#
    .SYNOPSIS  Run collect_overhead.py on the Pi4 via SSH.
    Returns the path to the local JSON output, or $null on failure.
    #>
    $phaseStart = Get-Date
    $remoteOut  = "/tmp/overhead_${Label}.json"

    Write-Host ""
    Write-Host "────────────────────────────────────────────────────────────" -ForegroundColor Yellow
    Write-Host "  Phase $Label : detector=$Detector, duration=${OverheadDuration}s" -ForegroundColor Yellow
    Write-Host "────────────────────────────────────────────────────────────" -ForegroundColor Yellow

    $cmd = "cd $DroneRepo && sudo -n -E $DetectorPython -u $OverheadScript --duration $OverheadDuration --detector $Detector --warmup 15 --output $remoteOut"
    Write-Host "  [SSH] $cmd" -ForegroundColor DarkGray

    # Run synchronously (blocks until done)
    $output = ssh -o ConnectTimeout=10 -o ServerAliveInterval=30 $DroneSsh $cmd 2>&1
    $exitCode = $LASTEXITCODE

    # Show output
    foreach ($line in ($output -split "`n")) {
        $line = $line.Trim()
        if ($line.Length -gt 0) {
            Write-Host "  [PI] $line"
        }
    }

    if ($exitCode -ne 0) {
        Write-Host "  Phase $Label FAILED (exit code $exitCode)" -ForegroundColor Red
        return $null
    }

    # SCP result to local
    $localDir = Join-Path $OutDir $Label
    if (!(Test-Path $localDir)) {
        New-Item -ItemType Directory -Path $localDir -Force | Out-Null
    }
    $localFile = Join-Path $localDir "overhead_${Label}.json"
    scp "${DroneSsh}:${remoteOut}" "$localFile" 2>&1 | Out-Null

    if (!(Test-Path $localFile)) {
        Write-Host "  Phase ${Label} - SCP failed" -ForegroundColor Red
        return $null
    }

    $elapsed = ((Get-Date) - $phaseStart).TotalMinutes
    Write-Host "  Phase $Label complete in $([math]::Round($elapsed, 1)) min -> $localFile" -ForegroundColor Green
    return $localFile
}

function Run-PqcPhase([string]$Label, [string]$SkipFlags) {
    <#
    .SYNOPSIS  Delegate to run_e2e_benchmark.ps1 for a single PQC phase.
    Returns the output directory path.
    #>
    $phaseStart = Get-Date
    Write-Host ""
    Write-Host "────────────────────────────────────────────────────────────" -ForegroundColor Cyan
    Write-Host "  Phase $Label : PQC tunnel benchmark" -ForegroundColor Cyan
    Write-Host "────────────────────────────────────────────────────────────" -ForegroundColor Cyan

    # Use hashtable splatting for named parameters (PS5.1 compatible)
    $pqcArgs = @{
        IntervalSec = $IntervalSec
        DroneSsh    = $DroneSsh
        CondaEnv    = $CondaEnv
        RunTag      = "${RunTag}_${Label}"
    }
    if ($MaxSuites -gt 0)    { $pqcArgs["MaxSuites"]  = $MaxSuites }
    if ($FilterAead -ne "")  { $pqcArgs["FilterAead"]  = $FilterAead }
    if ($FilterKem -ne "")   { $pqcArgs["FilterKem"]   = $FilterKem }

    # Add phase-specific skip flags as switch parameters
    foreach ($flag in ($SkipFlags -split " ")) {
        if ($flag) { $pqcArgs[$flag] = $true }
    }

    Write-Host "  Calling run_e2e_benchmark.ps1 with: $($pqcArgs.Keys | ForEach-Object { '-' + $_ + ' ' + $pqcArgs[$_] })" -ForegroundColor DarkGray
    & $E2EScript @pqcArgs

    $elapsed = ((Get-Date) - $phaseStart).TotalMinutes
    Write-Host "  Phase $Label complete in $([math]::Round($elapsed, 1)) min" -ForegroundColor Green

    # Copy results to our output dir
    $srcDir = Join-Path $RepoRoot "logs\benchmarks\runs\${RunTag}_${Label}"
    $dstDir = Join-Path $OutDir $Label
    if (Test-Path $srcDir) {
        if (!(Test-Path $dstDir)) {
            New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
        }
        Copy-Item -Path "$srcDir\*" -Destination $dstDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    return $dstDir
}

# ── Pre-flight ───────────────────────────────────────────────────────

Write-Host "── Pre-flight checks ──" -ForegroundColor Yellow
if (!(Test-SshOk)) {
    Write-Host "ERROR: Cannot reach drone at $DroneSsh" -ForegroundColor Red
    exit 1
}
Write-Host "  SSH: OK" -ForegroundColor Green

# Verify overhead script exists on Pi
$remoteCheck = ssh -o ConnectTimeout=10 $DroneSsh "test -f $DroneRepo/$OverheadScript && echo OK" 2>&1
if ($remoteCheck -notmatch "OK") {
    Write-Host "  WARNING: $OverheadScript not found on Pi — SCP it first" -ForegroundColor Yellow
    Write-Host "  Copying benchmarks/ to Pi..." -NoNewline
    scp -r (Join-Path $RepoRoot "benchmarks") "${DroneSsh}:${DroneRepo}/" 2>&1 | Out-Null
    Write-Host " done"
}

# Verify E2E script exists
if (!(Test-Path $E2EScript)) {
    Write-Host "ERROR: run_e2e_benchmark.ps1 not found at $E2EScript" -ForegroundColor Red
    exit 1
}
Write-Host "  E2E script: OK" -ForegroundColor Green

Kill-AllBenchProcesses

if (!(Test-Path $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}

$phaseResults = @{}
$globalStart = Get-Date

# ══════════════════════════════════════════════════════════════════════
#  PHASE A: BASELINE (no PQC, no DDoS)
# ══════════════════════════════════════════════════════════════════════

if (!$SkipOverhead) {
    $r = Run-OverheadPhase -Label "A_baseline" -Detector "none"
    $phaseResults["A_baseline"] = $r

    Write-Host "  Cool-down 120s (thermal recovery)..." ; Start-Sleep -Seconds 120

    # ══════════════════════════════════════════════════════════════════
    #  PHASE B1: DDoS-only XGBoost (no PQC)
    # ══════════════════════════════════════════════════════════════════
    if (!$SkipXgb) {
        $r = Run-OverheadPhase -Label "B1_xgb_only" -Detector "xgboost"
        $phaseResults["B1_xgb_only"] = $r

        Write-Host "  Cool-down 120s (thermal recovery)..." ; Start-Sleep -Seconds 120
    }

    # ══════════════════════════════════════════════════════════════════
    #  PHASE B2: DDoS-only TST (no PQC)
    # ══════════════════════════════════════════════════════════════════
    if (!$SkipTst) {
        $r = Run-OverheadPhase -Label "B2_tst_only" -Detector "tst"
        $phaseResults["B2_tst_only"] = $r

        Write-Host "  Cool-down 120s (thermal recovery)..." ; Start-Sleep -Seconds 120
    }
}

# ══════════════════════════════════════════════════════════════════════
#  PHASE C: PQC-only (72 suites, no detector)
# ══════════════════════════════════════════════════════════════════════

if (!$SkipPqcOnly) {
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "  PHASE C: PQC tunnel only (no DDoS detector)" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan

    $r = Run-PqcPhase -Label "C_pqc_only" -SkipFlags "SkipXgb SkipTst"
    $phaseResults["C_pqc_only"] = $r

    Write-Host "  Cool-down 120s (thermal recovery)..." ; Start-Sleep -Seconds 120
}

# ══════════════════════════════════════════════════════════════════════
#  PHASE D: PQC + XGBoost
# ══════════════════════════════════════════════════════════════════════

if (!$SkipXgb) {
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "  PHASE D: PQC tunnel + XGBoost detector" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan

    $r = Run-PqcPhase -Label "D_pqc_xgb" -SkipFlags "SkipBaseline SkipTst"
    $phaseResults["D_pqc_xgb"] = $r

    Write-Host "  Cool-down 120s (thermal recovery)..." ; Start-Sleep -Seconds 120
}

# ══════════════════════════════════════════════════════════════════════
#  PHASE E: PQC + TST
# ══════════════════════════════════════════════════════════════════════

if (!$SkipTst) {
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "  PHASE E: PQC tunnel + TransformerIDS detector" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan

    $r = Run-PqcPhase -Label "E_pqc_tst" -SkipFlags "SkipBaseline SkipXgb"
    $phaseResults["E_pqc_tst"] = $r
}

# ══════════════════════════════════════════════════════════════════════
#  COMPARISON SUMMARY
# ══════════════════════════════════════════════════════════════════════

$totalElapsed = ((Get-Date) - $globalStart).TotalMinutes

Write-Host ""
Write-Host "================================================================" -ForegroundColor Magenta
Write-Host "  5-PHASE BENCHMARK COMPLETE" -ForegroundColor Magenta
Write-Host "  Total time: $([math]::Round($totalElapsed, 1)) minutes" -ForegroundColor Magenta
Write-Host "================================================================" -ForegroundColor Magenta
Write-Host ""

# Build comparison summary from overhead phases
$comparisonData = @{}
foreach ($key in $phaseResults.Keys) {
    $file = $phaseResults[$key]
    if ($file -and (Test-Path $file)) {
        try {
            $data = Get-Content $file -Raw | ConvertFrom-Json
            $comparisonData[$key] = @{
                "cpu_mean"   = $data.cpu.mean
                "temp_mean"  = $data.temperature_c.mean
                "power_mean" = $data.power_mw.mean
                "ram_mean"   = $data.ram_mb.mean
            }
        } catch {
            $comparisonData[$key] = @{ "error" = "parse_failed" }
        }
    } elseif ($file) {
        # PQC phases don't return a single file — count suite JSONs
        if (Test-Path $file) {
            $jsonCount = (Get-ChildItem $file -Filter "*.json" -Recurse -ErrorAction SilentlyContinue).Count
            $comparisonData[$key] = @{ "suite_jsons" = $jsonCount }
        }
    }
}

# Print overhead comparison table if phases A-B were run
if (!$SkipOverhead -and $comparisonData.ContainsKey("A_baseline")) {
    Write-Host "  +------------------+---------+---------+----------+---------+" -ForegroundColor White
    Write-Host "  | Phase            | CPU %   | Temp  C | Power mW | RAM MB  |" -ForegroundColor White
    Write-Host "  +------------------+---------+---------+----------+---------+" -ForegroundColor White

    $phases = @("A_baseline", "B1_xgb_only", "B2_tst_only")
    foreach ($p in $phases) {
        if ($comparisonData.ContainsKey($p)) {
            $d = $comparisonData[$p]
            $cpuStr   = $(if ($null -ne $d.cpu_mean)   { "{0,6:F1}" -f $d.cpu_mean }   else { "   N/A" })
            $tempStr  = $(if ($null -ne $d.temp_mean)   { "{0,6:F1}" -f $d.temp_mean }  else { "   N/A" })
            $powerStr = $(if ($null -ne $d.power_mean)  { "{0,7:F0}" -f $d.power_mean } else { "    N/A" })
            $ramStr   = $(if ($null -ne $d.ram_mean)    { "{0,6:F0}" -f $d.ram_mean }   else { "   N/A" })
            $label = $p.PadRight(16)
            Write-Host "  | $label | $cpuStr | $tempStr | $powerStr | $ramStr |"
        }
    }
    Write-Host "  +------------------+---------+---------+----------+---------+" -ForegroundColor White

    # Delta table
    $bl = $comparisonData["A_baseline"]
    if ($bl.cpu_mean) {
        Write-Host ""
        Write-Host "  Overhead deltas vs baseline:" -ForegroundColor Yellow
        foreach ($p in @("B1_xgb_only", "B2_tst_only")) {
            if ($comparisonData.ContainsKey($p)) {
                $d = $comparisonData[$p]
                $dCpu   = $(if ($d.cpu_mean -and $bl.cpu_mean)     { $d.cpu_mean - $bl.cpu_mean }     else { $null })
                $dTemp  = $(if ($d.temp_mean -and $bl.temp_mean)   { $d.temp_mean - $bl.temp_mean }   else { $null })
                $dPower = $(if ($d.power_mean -and $bl.power_mean) { $d.power_mean - $bl.power_mean } else { $null })
                $dRam   = $(if ($d.ram_mean -and $bl.ram_mean)     { $d.ram_mean - $bl.ram_mean }     else { $null })

                $label = $p.Replace("_only", "")
                Write-Host "    $label : " -NoNewline
                if ($null -ne $dCpu)   { Write-Host "CPU +$([math]::Round($dCpu,1))%  " -NoNewline -ForegroundColor $(if ($dCpu -gt 50) {"Red"} else {"Yellow"}) }
                if ($null -ne $dTemp)  { Write-Host "Temp +$([math]::Round($dTemp,1))°C  " -NoNewline }
                if ($null -ne $dPower) { Write-Host "Power +$([math]::Round($dPower,0))mW  " -NoNewline }
                if ($null -ne $dRam)   { Write-Host "RAM +$([math]::Round($dRam,0))MB" -NoNewline }
                Write-Host ""
            }
        }
    }
}

# PQC phase summary
Write-Host ""
Write-Host "  PQC Phase Results:" -ForegroundColor Yellow
foreach ($p in @("C_pqc_only", "D_pqc_xgb", "E_pqc_tst")) {
    $dir = Join-Path $OutDir $p
    if (Test-Path $dir) {
        $jsonCount = (Get-ChildItem $dir -Filter "*.json" -Recurse -ErrorAction SilentlyContinue).Count
        $color = $(if ($jsonCount -ge 72) {"Green"} elseif ($jsonCount -gt 0) {"Yellow"} else {"Red"})
        Write-Host "    $p : $jsonCount suite JSONs" -ForegroundColor $color
    } else {
        Write-Host "    $p : SKIPPED" -ForegroundColor DarkGray
    }
}

# Save comparison summary
$summaryFile = Join-Path $OutDir "comparison_summary.json"
$summaryObj = @{
    run_tag     = $RunTag
    total_min   = [math]::Round($totalElapsed, 1)
    phases      = $comparisonData
    parameters  = @{
        overhead_duration_s = $OverheadDuration
        pqc_interval_s      = $IntervalSec
        max_suites          = $MaxSuites
        filter_aead         = $FilterAead
        filter_kem          = $FilterKem
    }
}
$summaryObj | ConvertTo-Json -Depth 5 | Set-Content $summaryFile -Encoding UTF8

Write-Host ""
Write-Host "  Full results : $OutDir" -ForegroundColor Cyan
Write-Host "  Summary JSON : $summaryFile" -ForegroundColor Cyan
Write-Host ""
