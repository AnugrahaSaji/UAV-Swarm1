# PQC Benchmark Dashboard

A **forensic-grade analysis dashboard** for Secure-Tunnel PQC benchmarks, running on the GCS.

## Overview

This dashboard consumes validated benchmark JSONL data and provides interactive visualization of post-quantum cryptographic suite performance metrics.

### Key Features

- **Suite Explorer**: Browse and filter all benchmark suites by KEM, signature, AEAD, and NIST level
- **Suite Detail**: Deep-dive into all 18 metric categories for any suite
- **Comparison View**: Side-by-side comparison of two suites with difference calculation
- **Power Analysis**: Energy consumption visualization and top consumers
- **Integrity Monitor**: Data quality warnings and issue detection

### Safety Features

- ⚠️ **"No causal inference implied"** banner on all pages
- 🏷️ **VERIFIED / CONDITIONAL / DEPRECATED** labels on all metrics
- ❌ Missing data shown as "—", never interpolated
- ✅ Schema validation on all API responses

## What This Dashboard Shows

- Run context and environment information
- Cryptographic suite identity (KEM, signature, AEAD)
- Handshake timing and success/failure
- Data plane packet statistics
- Power consumption and energy (INA219 sensor)
- MAVLink integrity metrics
- Drone system resources (CPU, memory, temperature)
- Validation results

## What This Dashboard Does NOT Claim

- **No causal relationships** between metrics
- **No interpolated data** - missing values are shown explicitly
- **No derived metrics** unless explicitly computed
- **No aggregation across suites** unless user explicitly selects it
- **No modifications** to the underlying benchmark data

## Quick Start

### Backend (FastAPI)

```powershell
cd c:\Users\burak\ptojects\secure-tunnel\dashboard\backend

# Install dependencies
pip install -r requirements.txt

# Start server
python -m uvicorn main:app --reload --port 8000
```

Backend runs at: `http://localhost:8000`  
API docs at: `http://localhost:8000/docs`

### Frontend (React)

```powershell
cd c:\Users\burak\ptojects\secure-tunnel\dashboard\frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Frontend runs at: `http://localhost:5173`

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check with suite count |
| `GET /api/runs` | List all benchmark runs |
| `GET /api/suites` | List suites with optional filters |
| `GET /api/suites/filters` | Get available filter values |
| `GET /api/suite/{key}` | Get detailed suite metrics |
| `GET /api/compare?suite_a=&suite_b=` | Compare two suites |
| `GET /api/metrics/schema` | Get schema field definitions |

## Data Sources

The dashboard reads JSONL files from:
- `forensic_metrics.jsonl` (main benchmark data)
- `validation_metrics_fixed.jsonl`
- `logs/benchmarks/*/gcs_suite_metrics.jsonl`

## Tech Stack

**Backend:**
- Python 3.11, FastAPI, Pydantic, Pandas, Uvicorn

**Frontend:**
- React 18, TypeScript, Vite, TailwindCSS, Recharts, Zustand

## Metric Categories

| Category | Description |
|----------|-------------|
| A | Run & Context |
| B | Suite Crypto Identity |
| C | Suite Lifecycle Timeline |
| D | Handshake Metrics |
| E | Crypto Primitive Breakdown |
| F | Rekey Metrics |
| G | Data Plane (Proxy Level) |
| H | Latency & Jitter |
| I | MAVProxy Drone |
| J | MAVProxy GCS (Pruned) |
| K | MAVLink Integrity |
| L | Flight Controller Telemetry |
| M | Control Plane (Scheduler) |
| N | System Resources - Drone |
| O | System Resources - GCS (Deprecated) |
| P | Power & Energy |
| Q | Observability |
| R | Validation |
