#!/usr/bin/env python3
"""
Deterministic Benchmarking Phase Orchestrator
bench/run_deterministic_phase.py

Executes the complete deterministic benchmarking phase for the PQC-secured
UAV telemetry research system.

Phases executed:
  Phase 5 — KEM/Signature/AEAD primitive benchmarks (200 iterations)
  Phase 6 — Suite handshake benchmarks (200 iterations, all 24 suites)
  Phase 7 — AEAD data-plane benchmarks (5000 packets, 1024-byte payload)

Design constraints (from GLOBAL RULES):
  - No fabricated values
  - No assumptions
  - No skipping combinations
  - Same order, same iteration counts, same measurement procedure every run
  - All results written to artifact directories
  - Progress logged with timestamps

Usage:
    source ~/cenv/bin/activate
    cd ~/secure-tunnel
    python bench/run_deterministic_phase.py [--phase 5|6|7|all]

Output directories:
    bench/primitive-results/   — Phase 5
    suite-benchmarks/          — Phase 6
    aead-benchmarks/           — Phase 7
    progress/                  — Timestamped progress logs
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PRIMITIVE_RESULTS_DIR = ROOT / "bench" / "primitive-results"
SUITE_BENCHMARKS_DIR  = ROOT / "suite-benchmarks"
AEAD_BENCHMARKS_DIR   = ROOT / "aead-benchmarks"
PROGRESS_DIR          = ROOT / "progress"

for d in (PRIMITIVE_RESULTS_DIR, SUITE_BENCHMARKS_DIR, AEAD_BENCHMARKS_DIR, PROGRESS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PRIMITIVE_ITERATIONS = 200
HANDSHAKE_ITERATIONS = 200
AEAD_PACKET_COUNT    = 5000
AEAD_PAYLOAD_BYTES   = 1024

# Deterministic execution order — never reordered between runs
AEAD_EXECUTION_ORDER: Tuple[str, ...] = (
    "aesgcm128",
    "aesgcm192",
    "aesgcm256",
    "aesccm128",
    "aesccm192",
    "aesccm256",
    "chacha20poly1305",
    "ascon128",
)

# ---------------------------------------------------------------------------
# Progress logger
# ---------------------------------------------------------------------------
_progress_path: Optional[Path] = None

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def progress_log(msg: str, level: str = "INFO") -> None:
    line = f"[{_ts()}] [{level}] {msg}"
    print(line, flush=True)
    if _progress_path is not None:
        with open(_progress_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

def _init_progress_log() -> None:
    global _progress_path
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    _progress_path = PROGRESS_DIR / f"deterministic_phase_{timestamp}.txt"
    with open(_progress_path, "w", encoding="utf-8") as fh:
        fh.write(f"Deterministic Benchmarking Phase\n")
        fh.write(f"Started: {_ts()}\n")
        fh.write(f"Host: {os.uname().nodename if hasattr(os, 'uname') else 'unknown'}\n")
        fh.write(f"Python: {sys.version.split()[0]}\n")
        fh.write("=" * 70 + "\n\n")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_stats(values: List[float]) -> Dict:
    """Compute mean/median/p95/p99/min/max from a list of floats."""
    if not values:
        return {"mean": None, "median": None, "p95": None, "p99": None,
                "min": None, "max": None, "count": 0}
    s = sorted(values)
    n = len(s)
    p95_idx = max(0, int(n * 0.95) - 1)
    p99_idx = max(0, int(n * 0.99) - 1)
    return {
        "mean":   statistics.mean(values),
        "median": statistics.median(values),
        "p95":    s[p95_idx],
        "p99":    s[p99_idx],
        "min":    s[0],
        "max":    s[-1],
        "count":  n,
    }

def save_json(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)

def _get_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()[:16] if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"

def _get_hostname() -> str:
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "unknown"

# ---------------------------------------------------------------------------
# OQS compatibility (mirrors benchmark_pqc.py compat layer exactly)
# ---------------------------------------------------------------------------
_KEM_CLASS = None
_SIG_CLASS = None
_OQS_INITIALIZED = False

def _init_oqs() -> None:
    global _KEM_CLASS, _SIG_CLASS, _OQS_INITIALIZED
    if _OQS_INITIALIZED:
        return
    _OQS_INITIALIZED = True

    import_errors: List[str] = []

    # Style 1: from oqs.oqs import ... (some pip installs)
    try:
        from oqs.oqs import KeyEncapsulation, Signature  # type: ignore
        _KEM_CLASS = KeyEncapsulation
        _SIG_CLASS = Signature
        return
    except (ImportError, AttributeError) as e:
        import_errors.append(f"oqs.oqs: {e}")

    # Style 2: from oqs import ... (some venv/conda installs)
    try:
        from oqs import KeyEncapsulation, Signature  # type: ignore
        _KEM_CLASS = KeyEncapsulation
        _SIG_CLASS = Signature
        return
    except (ImportError, AttributeError) as e:
        import_errors.append(f"oqs: {e}")

    # Style 3: import oqs; oqs.X (attribute access)
    try:
        import oqs  # type: ignore
        _KEM_CLASS = oqs.KeyEncapsulation
        _SIG_CLASS = oqs.Signature
        return
    except (ImportError, AttributeError) as e:
        import_errors.append(f"oqs module attr: {e}")

    raise ImportError(f"Could not import OQS. Tried: {'; '.join(import_errors)}")


def _kem_class():
    _init_oqs()
    if _KEM_CLASS is None:
        raise ImportError("OQS KeyEncapsulation not available")
    return _KEM_CLASS

def _sig_class():
    _init_oqs()
    if _SIG_CLASS is None:
        raise ImportError("OQS Signature not available")
    return _SIG_CLASS

# ---------------------------------------------------------------------------
# PHASE 5 — Primitive benchmarks
# ---------------------------------------------------------------------------

def _bench_kem_primitive(oqs_name: str, iterations: int) -> Dict:
    """Run KEM keygen+encap+decap for `iterations` iterations and return stats."""
    KEM = _kem_class()
    encap_ns: List[float] = []
    decap_ns: List[float] = []
    keygen_ns: List[float] = []
    errors: List[str] = []

    progress_log(f"    KEM {oqs_name}: {iterations} iter keygen/encap/decap")

    for i in range(iterations):
        try:
            # keygen
            t0 = time.perf_counter_ns()
            kem = KEM(oqs_name)
            pub = kem.generate_keypair()
            keygen_ns.append(float(time.perf_counter_ns() - t0))

            # encap
            t0 = time.perf_counter_ns()
            ct, ss_enc = kem.encap_secret(pub)
            encap_ns.append(float(time.perf_counter_ns() - t0))

            # decap
            t0 = time.perf_counter_ns()
            ss_dec = kem.decap_secret(ct)
            decap_ns.append(float(time.perf_counter_ns() - t0))

            if ss_enc != ss_dec:
                errors.append(f"iter {i}: shared-secret mismatch")
            kem.free()
        except Exception as exc:
            errors.append(f"iter {i}: {exc}")

    return {
        "algorithm": oqs_name,
        "algorithm_type": "KEM",
        "iterations": iterations,
        "errors": errors,
        "keygen": compute_stats(keygen_ns),
        "encap": compute_stats(encap_ns),
        "decap": compute_stats(decap_ns),
    }


def _bench_sig_primitive(oqs_name: str, iterations: int) -> Dict:
    """Run Signature keygen+sign+verify for `iterations` iterations."""
    SIG = _sig_class()
    keygen_ns: List[float] = []
    sign_ns: List[float] = []
    verify_ns: List[float] = []
    errors: List[str] = []
    MESSAGE = b"benchmark-message-uav-telemetry-pqc"

    progress_log(f"    SIG {oqs_name}: {iterations} iter keygen/sign/verify")

    for i in range(iterations):
        try:
            t0 = time.perf_counter_ns()
            signer = SIG(oqs_name)
            pub_key = signer.generate_keypair()
            keygen_ns.append(float(time.perf_counter_ns() - t0))

            t0 = time.perf_counter_ns()
            sig = signer.sign(MESSAGE)
            sign_ns.append(float(time.perf_counter_ns() - t0))

            verifier = SIG(oqs_name)
            t0 = time.perf_counter_ns()
            ok = verifier.verify(MESSAGE, sig, pub_key)
            verify_ns.append(float(time.perf_counter_ns() - t0))

            if not ok:
                errors.append(f"iter {i}: signature verification failed")
            signer.free()
            verifier.free()
        except Exception as exc:
            errors.append(f"iter {i}: {exc}")

    return {
        "algorithm": oqs_name,
        "algorithm_type": "SIG",
        "iterations": iterations,
        "errors": errors,
        "keygen": compute_stats(keygen_ns),
        "sign": compute_stats(sign_ns),
        "verify": compute_stats(verify_ns),
    }


def _bench_aead_primitive(token: str, iterations: int) -> Dict:
    """Run AEAD encrypt+decrypt for `iterations` iterations, multiple payload sizes."""
    from core.aead import _instantiate_aead, required_key_length_for_aead

    PAYLOAD_SIZES = [64, 256, 1024, 4096]
    AAD = b"uav-benchmark-aad"
    results_by_size: Dict[int, Dict] = {}
    errors: List[str] = []

    progress_log(f"    AEAD {token}: {iterations} iter @ {PAYLOAD_SIZES} bytes")

    for payload_size in PAYLOAD_SIZES:
        plaintext = bytes(range(payload_size % 256)) * (payload_size // 256 + 1)
        plaintext = plaintext[:payload_size]
        enc_ns: List[float] = []
        dec_ns: List[float] = []

        for i in range(iterations):
            try:
                key_len = required_key_length_for_aead(token)
                key = bytes(range(key_len % 256)) * (key_len // 256 + 1)
                key = key[:key_len]
                epoch = (i >> 8) & 0xFF
                seq   = i & 0xFFFF
                nonce = bytes([epoch & 0xFF]) + seq.to_bytes(11, "big")

                cipher, nonce_len = _instantiate_aead(token, key)
                if nonce_len == 16:
                    nonce = nonce + b"\x00\x00\x00\x00"

                t0 = time.perf_counter_ns()
                ct = cipher.encrypt(nonce, plaintext, AAD)
                enc_ns.append(float(time.perf_counter_ns() - t0))

                t0 = time.perf_counter_ns()
                pt = cipher.decrypt(nonce, ct, AAD)
                dec_ns.append(float(time.perf_counter_ns() - t0))

                if pt != plaintext:
                    errors.append(f"{token} size={payload_size} iter={i}: plaintext mismatch")

            except Exception as exc:
                errors.append(f"{token} size={payload_size} iter={i}: {exc}")

        results_by_size[payload_size] = {
            "payload_bytes": payload_size,
            "encrypt": compute_stats(enc_ns),
            "decrypt": compute_stats(dec_ns),
        }

    return {
        "algorithm": token,
        "algorithm_type": "AEAD",
        "iterations": iterations,
        "errors": errors,
        "payload_results": results_by_size,
    }


def run_phase5(suite_registry: Dict, aead_registry: Dict) -> Dict:
    """Phase 5: primitive benchmarks — KEM, Signature, AEAD."""
    progress_log("=" * 60)
    progress_log("PHASE 5: PRIMITIVE BENCHMARKS")
    progress_log(f"  Iterations: {PRIMITIVE_ITERATIONS}")
    progress_log("=" * 60)

    git_commit = _get_git_commit()
    hostname   = _get_hostname()
    ts_start   = _ts()

    # --- KEM primitives ---
    kem_names_seen = set()
    kem_names_ordered: List[str] = []
    for suite in suite_registry.values():
        kem = str(suite.get("kem_name", ""))
        if kem and kem not in kem_names_seen:
            kem_names_seen.add(kem)
            kem_names_ordered.append(kem)

    progress_log(f"KEMs to benchmark: {len(kem_names_ordered)}")
    kem_results: List[Dict] = []
    for kem_name in kem_names_ordered:
        try:
            r = _bench_kem_primitive(kem_name, PRIMITIVE_ITERATIONS)
            r["git_commit"] = git_commit
            r["hostname"] = hostname
            r["timestamp_iso"] = _ts()
            kem_results.append(r)
            progress_log(f"    {kem_name}: encap_mean={r['encap']['mean']:.0f}ns  "
                         f"decap_mean={r['decap']['mean']:.0f}ns  "
                         f"errors={len(r['errors'])}")
        except Exception as exc:
            progress_log(f"    [FAIL] {kem_name}: {exc}", "ERROR")
            kem_results.append({"algorithm": kem_name, "error": str(exc)})

    # --- Signature primitives ---
    sig_names_seen = set()
    sig_names_ordered: List[str] = []
    for suite in suite_registry.values():
        sig = str(suite.get("sig_name", ""))
        if sig and sig not in sig_names_seen:
            sig_names_seen.add(sig)
            sig_names_ordered.append(sig)

    progress_log(f"Signatures to benchmark: {len(sig_names_ordered)}")
    sig_results: List[Dict] = []
    for sig_name in sig_names_ordered:
        try:
            r = _bench_sig_primitive(sig_name, PRIMITIVE_ITERATIONS)
            r["git_commit"] = git_commit
            r["hostname"] = hostname
            r["timestamp_iso"] = _ts()
            sig_results.append(r)
            progress_log(f"    {sig_name}: sign_mean={r['sign']['mean']:.0f}ns  "
                         f"verify_mean={r['verify']['mean']:.0f}ns  "
                         f"errors={len(r['errors'])}")
        except Exception as exc:
            progress_log(f"    [FAIL] {sig_name}: {exc}", "ERROR")
            sig_results.append({"algorithm": sig_name, "error": str(exc)})

    # --- AEAD primitives ---
    progress_log(f"AEADs to benchmark: {len(AEAD_EXECUTION_ORDER)}")
    aead_results: List[Dict] = []
    for token in AEAD_EXECUTION_ORDER:
        try:
            r = _bench_aead_primitive(token, PRIMITIVE_ITERATIONS)
            r["git_commit"] = git_commit
            r["hostname"] = hostname
            r["timestamp_iso"] = _ts()
            aead_results.append(r)
            p1024 = r["payload_results"].get(1024, {})
            enc_mean = (p1024.get("encrypt") or {}).get("mean")
            dec_mean = (p1024.get("decrypt") or {}).get("mean")
            enc_str = f"{enc_mean:.0f}ns" if enc_mean is not None else "n/a"
            dec_str = f"{dec_mean:.0f}ns" if dec_mean is not None else "n/a"
            progress_log(f"    {token}: enc@1024={enc_str}  dec@1024={dec_str}  "
                         f"errors={len(r['errors'])}")
        except Exception as exc:
            progress_log(f"    [FAIL] {token}: {exc}", "ERROR")
            aead_results.append({"algorithm": token, "error": str(exc)})

    # Build combined artifact
    artifact = {
        "phase": "5",
        "phase_description": "primitive_benchmarks",
        "hostname": hostname,
        "git_commit": git_commit,
        "timestamp_start_iso": ts_start,
        "timestamp_end_iso": _ts(),
        "primitive_iterations": PRIMITIVE_ITERATIONS,
        "kem": kem_results,
        "signature": sig_results,
        "aead": aead_results,
    }

    out_path = PRIMITIVE_RESULTS_DIR / "raw-results.json"
    save_json(artifact, out_path)
    progress_log(f"Phase 5 artifact written: {out_path}")

    # Also write individual files per primitive
    for r in kem_results:
        name = r["algorithm"].lower().replace("-", "_").replace(" ", "_")
        save_json(r, PRIMITIVE_RESULTS_DIR / f"kem_{name}.json")
    for r in sig_results:
        name = r["algorithm"].lower().replace("-", "_").replace(" ", "_").replace("+", "plus")
        save_json(r, PRIMITIVE_RESULTS_DIR / f"sig_{name}.json")
    for r in aead_results:
        save_json(r, PRIMITIVE_RESULTS_DIR / f"aead_{r['algorithm']}.json")

    return artifact


# ---------------------------------------------------------------------------
# PHASE 6 — Suite handshake benchmarks
# ---------------------------------------------------------------------------

def run_phase6(suite_registry: Dict) -> Dict:
    """Phase 6: suite handshake benchmarks — all suites, 200 iterations each."""
    from core.handshake import (
        generate_handshake_keys,
        build_hello,
        parse_hello,
        encapsulate_response,
        decapsulate_response,
    )

    progress_log("=" * 60)
    progress_log("PHASE 6: SUITE HANDSHAKE BENCHMARKS")
    progress_log(f"  Suites: {len(suite_registry)}")
    progress_log(f"  Iterations: {HANDSHAKE_ITERATIONS}")
    progress_log("=" * 60)

    git_commit = _get_git_commit()
    hostname   = _get_hostname()
    ts_start   = _ts()

    suite_results: Dict[str, Dict] = {}
    # Deterministic order: sorted suite_ids
    ordered_ids = sorted(suite_registry.keys())

    for suite_id in ordered_ids:
        suite = suite_registry[suite_id]
        progress_log(f"  Suite: {suite_id}  ({suite.get('kem_name')} x {suite.get('sig_name')})")

        wall_times_ns: List[float] = []
        errors: List[str] = []
        public_key_bytes: Optional[int] = None
        ciphertext_bytes: Optional[int] = None
        signature_bytes:  Optional[int] = None
        shared_secret_bytes: Optional[int] = None

        for i in range(HANDSHAKE_ITERATIONS):
            try:
                t0 = time.perf_counter_ns()

                # Initiator: generate keys + build hello
                kem_pub, kem_priv, sig_pub, sig_priv = generate_handshake_keys(suite_id)
                hello = build_hello(suite_id, kem_pub, sig_pub, sig_priv)
                parsed = parse_hello(hello)

                # Responder: encapsulate
                kem_ct, gcs_ss = encapsulate_response(parsed)

                # Initiator: decapsulate
                drone_ss = decapsulate_response(kem_ct, kem_priv)

                elapsed = float(time.perf_counter_ns() - t0)
                wall_times_ns.append(elapsed)

                if gcs_ss != drone_ss:
                    errors.append(f"iter {i}: shared-secret mismatch")

                if i == 0:
                    public_key_bytes   = len(kem_pub)
                    ciphertext_bytes   = len(kem_ct)
                    signature_bytes    = len(hello.signature) if hasattr(hello, "signature") else None
                    shared_secret_bytes = len(drone_ss)

            except Exception as exc:
                errors.append(f"iter {i}: {exc}")

        stats = compute_stats(wall_times_ns)
        progress_log(f"    mean={stats['mean']:.0f}ns  p95={stats['p95']:.0f}ns  "
                     f"errors={len(errors)}/{HANDSHAKE_ITERATIONS}")

        result = {
            "algorithm_name": suite_id,
            "algorithm_type": "SUITE",
            "operation": "full_handshake",
            "payload_size": None,
            "git_commit": git_commit,
            "hostname": hostname,
            "timestamp_iso": _ts(),
            "public_key_bytes": public_key_bytes,
            "secret_key_bytes": None,
            "ciphertext_bytes": ciphertext_bytes,
            "signature_bytes": signature_bytes,
            "shared_secret_bytes": shared_secret_bytes,
            "iterations_count": HANDSHAKE_ITERATIONS,
            "errors": errors,
            "stats": stats,
        }
        suite_results[suite_id] = result

        # Write individual file to suite-benchmarks/
        fname = suite_id.replace("-", "_") + "_full_handshake.json"
        save_json(result, SUITE_BENCHMARKS_DIR / fname)
        progress_log(f"    Written: {SUITE_BENCHMARKS_DIR / fname}")

    artifact = {
        "phase": "6",
        "phase_description": "suite_handshake_benchmarks",
        "hostname": hostname,
        "git_commit": git_commit,
        "timestamp_start_iso": ts_start,
        "timestamp_end_iso": _ts(),
        "handshake_iterations": HANDSHAKE_ITERATIONS,
        "suite_count": len(suite_results),
        "suites": suite_results,
    }

    save_json(artifact, SUITE_BENCHMARKS_DIR / "summary.json")
    progress_log(f"Phase 6 summary written: {SUITE_BENCHMARKS_DIR / 'summary.json'}")
    return artifact


# ---------------------------------------------------------------------------
# PHASE 7 — AEAD data-plane benchmark
# ---------------------------------------------------------------------------

def _bench_aead_dataplane(token: str) -> Dict:
    """Benchmark AEAD at 1024-byte payload, AEAD_PACKET_COUNT packets."""
    from core.aead import _instantiate_aead, required_key_length_for_aead

    PAYLOAD = bytes(range(256)) * (AEAD_PAYLOAD_BYTES // 256 + 1)
    PAYLOAD = PAYLOAD[:AEAD_PAYLOAD_BYTES]
    AAD = b"mav-telemetry-bench"
    enc_ns: List[float] = []
    dec_ns: List[float] = []
    errors: List[str] = []

    progress_log(f"    AEAD data-plane {token}: {AEAD_PACKET_COUNT} × {AEAD_PAYLOAD_BYTES}B")

    key_len = required_key_length_for_aead(token)
    import hashlib
    key = hashlib.sha256(f"bench-key-{token}".encode()).digest()[:key_len]
    key = key.ljust(key_len, b"\x00")[:key_len]

    cipher, nonce_len = _instantiate_aead(token, key)

    for i in range(AEAD_PACKET_COUNT):
        epoch = (i >> 16) & 0xFF
        seq   = i & 0xFFFFFF
        nonce = bytes([epoch]) + seq.to_bytes(nonce_len - 1, "big")

        try:
            t0 = time.perf_counter_ns()
            ct = cipher.encrypt(nonce, PAYLOAD, AAD)
            enc_ns.append(float(time.perf_counter_ns() - t0))

            t0 = time.perf_counter_ns()
            pt = cipher.decrypt(nonce, ct, AAD)
            dec_ns.append(float(time.perf_counter_ns() - t0))

            if pt != PAYLOAD:
                errors.append(f"pkt {i}: plaintext mismatch")
        except Exception as exc:
            errors.append(f"pkt {i}: {exc}")

    return {
        "algorithm": token,
        "payload_bytes": AEAD_PAYLOAD_BYTES,
        "packet_count": AEAD_PACKET_COUNT,
        "errors": errors,
        "encrypt": compute_stats(enc_ns),
        "decrypt": compute_stats(dec_ns),
    }


def run_phase7() -> Dict:
    """Phase 7: AEAD data-plane benchmarks (5000 packets, 1024-byte payload)."""
    progress_log("=" * 60)
    progress_log("PHASE 7: AEAD DATA-PLANE BENCHMARKS")
    progress_log(f"  Packets: {AEAD_PACKET_COUNT}")
    progress_log(f"  Payload: {AEAD_PAYLOAD_BYTES} bytes")
    progress_log(f"  AEADs:   {len(AEAD_EXECUTION_ORDER)}")
    progress_log("=" * 60)

    git_commit = _get_git_commit()
    hostname   = _get_hostname()
    ts_start   = _ts()

    aead_results: List[Dict] = []
    supported: List[str]  = []
    unsupported: List[str] = []

    for token in AEAD_EXECUTION_ORDER:
        try:
            r = _bench_aead_dataplane(token)
            r["git_commit"] = git_commit
            r["hostname"] = hostname
            r["timestamp_iso"] = _ts()
            aead_results.append(r)
            supported.append(token)
            enc_mean = r["encrypt"]["mean"]
            dec_mean = r["decrypt"]["mean"]
            progress_log(f"    {token}: enc_mean={enc_mean:.0f}ns  "
                         f"dec_mean={dec_mean:.0f}ns  errors={len(r['errors'])}")

            # Store per-AEAD directory (mirrors mavlink-benchmark-report/ layout)
            aead_dir = AEAD_BENCHMARKS_DIR / token
            aead_dir.mkdir(parents=True, exist_ok=True)
            save_json(r, aead_dir / "dataplane-result.json")

        except Exception as exc:
            progress_log(f"    [FAIL] {token}: {exc}", "ERROR")
            err_entry = {
                "algorithm": token,
                "payload_bytes": AEAD_PAYLOAD_BYTES,
                "packet_count": AEAD_PACKET_COUNT,
                "error": str(exc),
                "git_commit": git_commit,
                "hostname": hostname,
                "timestamp_iso": _ts(),
            }
            aead_results.append(err_entry)
            unsupported.append(token)
            aead_dir = AEAD_BENCHMARKS_DIR / token
            aead_dir.mkdir(parents=True, exist_ok=True)
            save_json(err_entry, aead_dir / "dataplane-result.json")

    artifact = {
        "phase": "7",
        "phase_description": "aead_dataplane_benchmarks",
        "hostname": hostname,
        "git_commit": git_commit,
        "timestamp_start_iso": ts_start,
        "timestamp_end_iso": _ts(),
        "packet_count": AEAD_PACKET_COUNT,
        "payload_bytes": AEAD_PAYLOAD_BYTES,
        "supported": supported,
        "unsupported": unsupported,
        "aead_results": aead_results,
    }

    save_json(artifact, AEAD_BENCHMARKS_DIR / "raw-results.json")
    progress_log(f"Phase 7 artifact written: {AEAD_BENCHMARKS_DIR / 'raw-results.json'}")
    return artifact


# ---------------------------------------------------------------------------
# Result validation (Step 11)
# ---------------------------------------------------------------------------

def validate_results(p5: Optional[Dict], p6: Optional[Dict], p7: Optional[Dict]) -> None:
    progress_log("=" * 60)
    progress_log("RESULT VALIDATION")
    progress_log("=" * 60)

    if p5:
        kem_ok  = sum(1 for r in p5.get("kem", [])       if "error" not in r)
        sig_ok  = sum(1 for r in p5.get("signature", []) if "error" not in r)
        aead_ok = sum(1 for r in p5.get("aead", [])      if "error" not in r)
        progress_log(f"Phase 5: KEM={kem_ok} OK  SIG={sig_ok} OK  AEAD={aead_ok} OK")
        # Anomaly check: look for high error rates
        for r in p5.get("kem", []) + p5.get("signature", []) + p5.get("aead", []):
            errs = r.get("errors", [])
            if errs:
                progress_log(f"  [ANOMALY] {r.get('algorithm')}: {len(errs)} errors", "WARN")

    if p6:
        suites_ok = sum(1 for r in p6.get("suites", {}).values() if not r.get("errors"))
        suites_total = len(p6.get("suites", {}))
        progress_log(f"Phase 6: {suites_ok}/{suites_total} suites clean")
        for sid, r in p6.get("suites", {}).items():
            errs = r.get("errors", [])
            if errs:
                progress_log(f"  [ANOMALY] {sid}: {len(errs)} errors", "WARN")

    if p7:
        supported   = p7.get("supported", [])
        unsupported = p7.get("unsupported", [])
        progress_log(f"Phase 7: {len(supported)} AEAD supported, {len(unsupported)} unsupported")
        for u in unsupported:
            progress_log(f"  [SKIPPED] {u}: recorded as unsupported — NOT discarded", "WARN")
        # aesgcm128 rekey collapse anomaly check (known from prior runs)
        for r in p7.get("aead_results", []):
            if r.get("algorithm") == "aesgcm128" and "error" not in r:
                progress_log("  NOTE: aesgcm128 packet-loss anomaly may appear in MAVLink e2e "
                             "(confirmed from prior MAVLink benchmark — not visible in isolation)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic Benchmarking Phase — PQC Secure Tunnel"
    )
    parser.add_argument(
        "--phase", default="all",
        choices=["5", "6", "7", "all"],
        help="Which phase to run (default: all)"
    )
    args = parser.parse_args()

    _init_progress_log()
    progress_log("Deterministic benchmarking phase started")
    progress_log(f"Running phase(s): {args.phase}")

    # Load suite registry once
    from core.suites import list_suites
    suite_registry = list_suites()
    progress_log(f"Suite registry loaded: {len(suite_registry)} suites")

    p5: Optional[Dict] = None
    p6: Optional[Dict] = None
    p7: Optional[Dict] = None
    start_wall = time.monotonic()

    try:
        if args.phase in ("5", "all"):
            from core.suites import benchmark_aead_tokens
            aead_reg = {t: {"token": t} for t in benchmark_aead_tokens()}
            p5 = run_phase5(suite_registry, aead_reg)
            progress_log(f"Phase 5 complete. Elapsed: {time.monotonic()-start_wall:.1f}s")

        if args.phase in ("6", "all"):
            p6 = run_phase6(suite_registry)
            progress_log(f"Phase 6 complete. Elapsed: {time.monotonic()-start_wall:.1f}s")

        if args.phase in ("7", "all"):
            p7 = run_phase7()
            progress_log(f"Phase 7 complete. Elapsed: {time.monotonic()-start_wall:.1f}s")

        validate_results(p5, p6, p7)

        # Final report (Step 14)
        progress_log("=" * 60)
        progress_log("FINAL REPORT")
        progress_log("=" * 60)
        if p5:
            progress_log(f"Primitives benchmarked: {len(p5.get('kem',[]))} KEM, "
                         f"{len(p5.get('signature',[]))} SIG, "
                         f"{len(p5.get('aead',[]))} AEAD")
        if p6:
            progress_log(f"Suites benchmarked: {p6.get('suite_count', 0)}")
        if p7:
            progress_log(f"AEAD data-plane tested: {len(p7.get('supported', []))} supported, "
                         f"{len(p7.get('unsupported', []))} unsupported")
        if p6 and p7:
            combos = p6.get("suite_count", 0) * len(p7.get("supported", []))
            progress_log(f"Total suite×AEAD combinations: {combos}")
        if p7:
            pkts = p7.get("packet_count", 0) * len(p7.get("supported", []))
            progress_log(f"Total data-plane packets processed: {pkts:,}")

        total_elapsed = time.monotonic() - start_wall
        progress_log(f"Total wall time: {total_elapsed:.1f}s ({total_elapsed/60:.1f}min)")
        progress_log("Benchmarking phase complete. Artifacts written to artifact directories.")

    except KeyboardInterrupt:
        progress_log("Interrupted by user. Partial results may be saved.", "WARN")
        raise
    except Exception as exc:
        progress_log(f"Fatal error: {exc}", "ERROR")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
