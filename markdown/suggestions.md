# Codebase Audit and Suggestions

**Date:** 2024-05-22
**Reviewer:** Jules (AI Software Engineer)

## 1. Executive Summary

The "Secure Tunnel" codebase is a well-structured research prototype for Post-Quantum Cryptography (PQC) on UAVs. It implements a "bump-in-the-wire" proxy architecture using `liboqs`. While the core cryptographic logic is sound, the control plane security and dependency management need improvement before production deployment. The system recently added a comprehensive metrics framework (18 categories, 231 metrics) which aligns well with research goals.

## 2. Organization & Structure

The codebase has been reorganized for clarity:
- **`markdown/`**: Contains all documentation (`.md` files).
- **`text-files/`**: Contains logs, audit findings, and raw text data.
- **`legacy_archive/`**: Contains redundant or deprecated scripts (`sdrone copy.py`, etc.).
- **`core/`**: The engine (crypto, handshake, proxy, metrics).
- **`sscheduler/`**: The active control plane (Drone-driven).
- **`bench/`**: Drivers for performance and power benchmarking.

## 3. Analysis Findings

### 3.1 Robustness
*   **Error Handling:** `core/async_proxy.py` uses broad `try-except` blocks around socket I/O. This is good for resilience but can mask specific logic errors. Recommendation: Log the specific exception types more granularly.
*   **Concurrency:** The `sscheduler` uses threading. The `TelemetryListener` and `LocalMonitor` appear thread-safe (using locks or detached threads), but the interaction between `DroneScheduler` policy evaluation and the GCS client is synchronous and blocking. Recommendation: Move GCS command sending to a non-blocking queue or async task to prevent scheduler stalls.
*   **Dependencies:** The system heavily relies on `liboqs` and its Python wrapper `oqs-python`. These are not standard pip packages and caused test failures in the CI environment. Recommendation: Create a Dockerfile or a robust `setup.sh` that compiles `liboqs` from source to ensure reproducible environments.

### 3.2 Comparison with Research Metrics
The documentation (`markdown/METRICS_FRAMEWORK.md`) defines a target of 231 metrics. The implementation in `core/metrics_schema.py` and `core/metrics_collectors.py` matches this specification almost exactly.
*   **Power:** `PowerCollector` supports `INA219` and `RPi5 PMIC`, covering the embedded use case.
*   **Latency:** `LatencyTracker` calculates p50/p95/p99, crucial for real-time flight control analysis.
*   **Crypto:** `CryptoPrimitiveBreakdown` captures nanosecond-precision timing for KEM/Sig operations, allowing detailed comparison of PQC algorithms (e.g., Kyber vs. McEliece).

### 3.3 Security Flaws
*   **Control Channel:** The TCP connection between `sdrone.py` and `sgcs.py` (port 48080) sends JSON commands in plaintext without authentication. **High Severity.**
    *   *Fix:* Wrap the control socket in TLS (using Python's `ssl` module) or implement an application-layer HMAC challenge similar to the data plane handshake.
*   **Secrets:** `core/config.py` allows a shared `DRONE_PSK`. While useful for research, a production system should use unique per-drone keys or certificates.

## 4. Suggestions for Improvement

### 4.1 Immediate Actions (Code Quality)
1.  **Type Hints:** Add Python type hints (`typing`) to `sscheduler/` files to improve maintainability. `core/` is already well-typed.
2.  **Linting:** Run `flake8` or `black` to enforce consistent style (indentation varies in some scripts).

### 4.2 Architectural Changes
1.  **AsyncIO:** `core/async_proxy.py` uses `selectors` (low-level). Migrating to Python's `asyncio` would make the code more readable and easier to integrate with modern web/networking libraries.
2.  **Telemetry Sync:** The `uav.pqc.telemetry.v1` schema is robust, but the *parsing* logic in `sdrone.py` relies on polling. Implementing a dedicated UDP listener thread that pushes updates to a queue (producer-consumer) would be more reliable.

### 4.3 Documentation
1.  **Build Guide:** A clear, step-by-step guide for compiling `liboqs` on Raspberry Pi and Windows is missing from the main documentation.
2.  **API Docs:** Auto-generate API docs from the docstrings in `core/`.

## 5. Conclusion

The system is in a strong state for a research prototype. The addition of the metrics framework makes it a powerful tool for PQC benchmarking. Addressing the control plane security and dependency management are the next critical steps.
