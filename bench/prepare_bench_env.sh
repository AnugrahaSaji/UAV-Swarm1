#!/usr/bin/env bash
#
# PQC Benchmark Environment Preparation Script
#
# Run this BEFORE benchmarking to ensure proper isolation.
#
# Usage:
#   sudo ./bench/prepare_bench_env.sh
#

set -euo pipefail

echo "=============================================="
echo "PQC BENCHMARK ENVIRONMENT PREPARATION"
echo "=============================================="
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "[ERROR] This script must be run as root (sudo)"
   exit 1
fi

# Get the user who invoked sudo
REAL_USER="${SUDO_USER:-$(whoami)}"

echo "[1/7] Checking hardware..."
echo "  Hostname: $(hostname)"
echo "  Kernel: $(uname -r)"
echo "  Architecture: $(uname -m)"

# CPU info
if [[ -f /proc/cpuinfo ]]; then
    CPU_MODEL=$(grep -m1 -E "^(Model|model name|Hardware)" /proc/cpuinfo | cut -d: -f2- | xargs || true)
    if [[ -z "${CPU_MODEL}" ]]; then
        CPU_MODEL=$(uname -m)
    fi
    CPU_CORES=$(grep -c "processor" /proc/cpuinfo)
    echo "  CPU: ${CPU_MODEL}"
    echo "  Cores: ${CPU_CORES}"
fi

echo ""

echo "[2/7] Setting CPU governor to 'performance'..."
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [[ -f "$cpu" ]]; then
        echo "performance" > "$cpu"
    fi
done

# Verify
GOVERNOR=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo "unknown")
echo "  Current governor: ${GOVERNOR}"

if [[ "${GOVERNOR}" != "performance" ]]; then
    echo "  [WARNING] Could not set performance governor"
fi

echo ""

echo "[3/7] Disabling CPU frequency scaling..."
# Disable turbo boost if available (Intel)
if [[ -f /sys/devices/system/cpu/intel_pstate/no_turbo ]]; then
    echo "1" > /sys/devices/system/cpu/intel_pstate/no_turbo
    echo "  Disabled Intel Turbo Boost"
fi

# ARM: Set max frequency
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq; do
    if [[ -f "$cpu" ]]; then
        MAX_FREQ=$(cat "${cpu}")
        echo "${MAX_FREQ}" > "${cpu%scaling_max_freq}scaling_min_freq" 2>/dev/null || true
    fi
done

echo "  Frequency scaling locked"
echo ""

echo "[4/7] Checking for running secure-tunnel services..."
# Check for existing processes
MAVPROXY_PIDS=$(pgrep -f mavproxy || true)
SCHEDULER_PIDS=$(pgrep -f "sscheduler|sdrone|sgcs" || true)
PROXY_PIDS=$(pgrep -f "async_proxy|run_proxy" || true)

if [[ -n "${MAVPROXY_PIDS}" ]]; then
    echo "  [WARNING] MAVProxy is running (PIDs: ${MAVPROXY_PIDS})"
    echo "            Consider stopping it: sudo pkill -f mavproxy"
fi

if [[ -n "${SCHEDULER_PIDS}" ]]; then
    echo "  [WARNING] Scheduler processes running (PIDs: ${SCHEDULER_PIDS})"
    echo "            Consider stopping: sudo pkill -f 'sscheduler|sdrone|sgcs'"
fi

if [[ -n "${PROXY_PIDS}" ]]; then
    echo "  [WARNING] Proxy processes running (PIDs: ${PROXY_PIDS})"
    echo "            Consider stopping: sudo pkill -f 'async_proxy|run_proxy'"
fi

if [[ -z "${MAVPROXY_PIDS}" && -z "${SCHEDULER_PIDS}" && -z "${PROXY_PIDS}" ]]; then
    echo "  No conflicting services detected"
fi

echo ""

echo "[5/7] Checking INA219 power sensor..."
# Check I2C availability
if command -v i2cdetect &>/dev/null; then
    I2C_BUS=""
    for bus in 0 1 2; do
        if i2cdetect -y "$bus" 2>/dev/null | grep -q "40"; then
            I2C_BUS="$bus"
            break
        fi
    done
    
    if [[ -n "${I2C_BUS}" ]]; then
        echo "  INA219 detected on I2C bus ${I2C_BUS} at address 0x40"
    else
        echo "  [INFO] INA219 not detected on I2C (power measurements will be null)"
    fi
else
    echo "  [INFO] i2cdetect not available (install i2c-tools to check INA219)"
fi

echo ""

echo "[6/7] Checking perf availability..."
if command -v perf &>/dev/null; then
    PERF_VERSION=$(perf version 2>&1 | head -1)
    echo "  ${PERF_VERSION}"
    
    # Check if perf can access counters
    if perf stat -e cycles true 2>&1 | grep -q "cycles"; then
        echo "  perf counters: available"
    else
        echo "  [WARNING] perf counters may require kernel.perf_event_paranoid=-1"
        echo "            Run: sudo sysctl -w kernel.perf_event_paranoid=-1"
    fi
else
    echo "  [WARNING] perf not installed"
    echo "            Install: sudo apt install linux-perf"
fi

# Enable perf for non-root
echo "-1" > /proc/sys/kernel/perf_event_paranoid 2>/dev/null || true

echo ""

echo "[7/7] Checking git status..."
cd "$(dirname "$0")/.." || exit 1

GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
GIT_DIRTY=$(git status --porcelain 2>/dev/null)

echo "  Commit: ${GIT_COMMIT:0:12}"
echo "  Branch: ${GIT_BRANCH}"

if [[ -n "${GIT_DIRTY}" ]]; then
    echo "  [WARNING] Working directory has uncommitted changes"
    echo "            Benchmark results should reference clean commits"
else
    echo "  Status: clean"
fi

echo ""

echo "[8/7] Reading temperature (if available)..."
TEMP=""
if [[ -f /sys/class/thermal/thermal_zone0/temp ]]; then
    TEMP_MILLIC=$(cat /sys/class/thermal/thermal_zone0/temp)
    TEMP=$(echo "scale=1; ${TEMP_MILLIC}/1000" | bc)
    echo "  CPU temperature: ${TEMP}°C"
else
    echo "  [INFO] Temperature sensor not available"
fi

echo ""
echo "=============================================="
echo "ENVIRONMENT PREPARATION COMPLETE"
echo "=============================================="
echo ""
echo "To run benchmarks:"
echo "  cd $(pwd)"
echo "  python bench/benchmark_pqc.py --iterations 200"
echo ""
echo "To pin to CPU core 0:"
echo "  taskset -c 0 python bench/benchmark_pqc.py --iterations 200"
echo ""
