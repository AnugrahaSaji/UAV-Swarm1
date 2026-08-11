#!/usr/bin/env bash
#
# PQC Benchmark Runner Script
#
# Full benchmark execution with environment preparation and isolation.
#
# Usage:
#   ./bench/run_benchmarks.sh [OPTIONS]
#
# Options:
#   --iterations N    Number of iterations (default: 200)
#   --output-dir DIR  Output directory (default: bench_results_TIMESTAMP)
#   --cpu-core N      CPU core to pin to (default: 0)
#   --skip-prep       Skip environment preparation
#

set -euo pipefail

# Defaults
ITERATIONS=200
OUTPUT_DIR=""
CPU_CORE=0
SKIP_PREP=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --iterations)
            ITERATIONS="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --cpu-core)
            CPU_CORE="$2"
            shift 2
            ;;
        --skip-prep)
            SKIP_PREP=1
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Generate output directory name if not specified
if [[ -z "${OUTPUT_DIR}" ]]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    OUTPUT_DIR="bench_results_${TIMESTAMP}"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"

# Virtual environment path (default for Raspberry Pi setup)
VENV_PATH="${HOME}/cenv"

echo "=============================================="
echo "PQC BENCHMARK RUNNER"
echo "=============================================="
echo ""
echo "Configuration:"
echo "  Iterations:   ${ITERATIONS}"
echo "  Output:       ${OUTPUT_DIR}"
echo "  CPU Core:     ${CPU_CORE}"
echo "  Project Dir:  ${PROJECT_DIR}"
echo "  VEnv Path:    ${VENV_PATH}"
echo ""

cd "${PROJECT_DIR}"

# Activate virtual environment if it exists
if [[ -f "${VENV_PATH}/bin/activate" ]]; then
    echo "Activating virtual environment: ${VENV_PATH}"
    source "${VENV_PATH}/bin/activate"
    echo ""
fi

# Environment preparation
if [[ ${SKIP_PREP} -eq 0 ]]; then
    echo "Running environment preparation..."
    echo "(This requires sudo privileges)"
    echo ""
    sudo bash "${SCRIPT_DIR}/prepare_bench_env.sh"
    echo ""
fi

# Check Python
echo "Checking Python environment..."
PYTHON_CMD="python3"
if ! command -v python3 &>/dev/null; then
    PYTHON_CMD="python"
fi

${PYTHON_CMD} --version
echo ""

# Check OQS
echo "Checking oqs-python..."
${PYTHON_CMD} -c "
try:
    from oqs import oqs_version
    print(f'oqs version: {oqs_version()}')
except ImportError:
    try:
        from oqs.oqs import oqs_version
        print(f'oqs version: {oqs_version()}')
    except ImportError:
        import oqs
        print(f'oqs version: {oqs.oqs_version()}')
" || {
    echo "[ERROR] oqs-python not available"
    exit 1
}
echo ""

# Pull latest code (optional)
echo "Git status:"
git status --short
echo ""

# Run benchmark with CPU pinning
echo "Starting benchmarks..."
echo "  Pinning to CPU core ${CPU_CORE}"
echo "  Output directory: ${OUTPUT_DIR}"
echo ""

START_TIME=$(date +%s)

taskset -c "${CPU_CORE}" ${PYTHON_CMD} "${SCRIPT_DIR}/benchmark_pqc.py" \
    --iterations "${ITERATIONS}" \
    --output-dir "${OUTPUT_DIR}"

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "=============================================="
echo "BENCHMARK RUN COMPLETE"
echo "=============================================="
echo ""
echo "Duration: ${ELAPSED} seconds"
echo "Results:  ${PROJECT_DIR}/${OUTPUT_DIR}"
echo ""

# List output files
echo "Output files:"
find "${OUTPUT_DIR}" -type f | head -20
TOTAL_FILES=$(find "${OUTPUT_DIR}" -type f | wc -l)
echo "  ... (${TOTAL_FILES} total files)"
echo ""
