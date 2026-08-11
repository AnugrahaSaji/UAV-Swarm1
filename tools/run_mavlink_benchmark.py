#!/usr/bin/env python3
"""
MAVLink Benchmark Report — Complete 8-AEAD Protocol (10-minute runs)
=====================================================================

Runs the full E2E MAVLink tunnel benchmark across all 8 AEAD cipher
configurations on the PQC secure tunnel, following the defined protocol:

  Phase 1  — Heartbeat continuity (1 Hz / 60 s)
  Phase 2  — PING RTT burst (1000 pings, 5 ms interval)
  Phase 3  — High-rate telemetry stress (50 Hz / 30 s)
  Phase 6  — Continuous traffic (10 min total, rekey at T+300 s)

AEAD Coverage:
  AES-GCM   aesgcm128 / aesgcm192 / aesgcm256   (NIST L1 / L3 / L5)
  AES-CCM   aesccm128 / aesccm192 / aesccm256   (NIST L1 / L3 / L5)
  Ascon     ascon128
  ChaCha20  chacha20poly1305

System Topology (localhost loopback):
  [GCS app] -> 47001 -> [GCS Proxy] -> encrypted UDP -> [Drone Proxy] -> 47004 -> [Drone app]
  [GCS app] <- 47002 <- [GCS Proxy] <- encrypted UDP <- [Drone Proxy] <- 47003 <- [Drone app]

Output directory (mavlink-benchmark-report/):
  mavlink-latency.md          — aggregated RTT/latency across all AEADs
  heartbeat-stability.md      — aggregated HB continuity across all AEADs
  rekey-events.md             — rekey event log for all AEADs
  link-quality.md             — overall link quality matrix
  raw-mavlink-log.json        — full raw results
  all-aead-summary.md         — combined summary table
  environment.md              — host/runtime snapshot
  <aead>/                     — per-AEAD sub-reports (per-phase .md + summary)

Usage:
  # Full 10-min protocol (all 8 AEADs, ~96 min total):
  python tools/run_mavlink_benchmark.py

  # Quick validation (shorter continuous window):
  python tools/run_mavlink_benchmark.py --continuous-warmup 30 --continuous-measure 30

  # Single AEAD:
  python tools/run_mavlink_benchmark.py --aead ascon128

Protocol version: 1.0 (FROZEN — no core modifications)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── Import all helpers from the existing bench module ─────────────────────────
_tools = ROOT / "tools"
_spec = importlib.util.spec_from_file_location(
    "run_mav_tunnel_bench",
    _tools / "run_mav_tunnel_bench.py",
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore
sys.modules["run_mav_tunnel_bench"] = _mod  # needed for dataclass __module__ resolution
_spec.loader.exec_module(_mod)  # type: ignore

from core.suites import DEFAULT_SUITE_ID

# ── AEAD–Suite level-matched pairs (PROTOCOL_VERSION 1.0) ────────────────────
# Each AEAD must be paired with the suite at the same NIST security level.
# Mixing levels (e.g. L1 AEAD + L3 suite) is rejected by the proxy core.
#
#   L1: aesgcm128, aesccm128, ascon128        → cs-mlkem512-mldsa44
#   L3: aesgcm192, aesccm192                  → cs-mlkem768-mldsa65  (DEFAULT)
#   L5: aesgcm256, aesccm256, chacha20poly1305 → cs-mlkem1024-mldsa87
AEAD_SUITE_PAIRS: List[tuple] = [
    ("aesgcm128",        "cs-mlkem512-mldsa44"),    # AES-GCM L1
    ("aesgcm192",        "cs-mlkem768-mldsa65"),    # AES-GCM L3
    ("aesgcm256",        "cs-mlkem1024-mldsa87"),   # AES-GCM L5
    ("aesccm128",        "cs-mlkem512-mldsa44"),    # AES-CCM L1
    ("aesccm192",        "cs-mlkem768-mldsa65"),    # AES-CCM L3
    ("aesccm256",        "cs-mlkem1024-mldsa87"),   # AES-CCM L5
    ("ascon128",         "cs-mlkem512-mldsa44"),    # Ascon-AEAD128 L1
    ("chacha20poly1305", "cs-mlkem1024-mldsa87"),   # ChaCha20-Poly1305 L5
]

# ── Per-phase timing ───────────────────────────────────────────────────────────
HB_DURATION_S       = 60.0    # Phase 1: heartbeat duration
HB_RATE_HZ          = 1.0     # Phase 1: heartbeat rate
PING_COUNT          = 1000    # Phase 2: ping burst count
PING_INTERVAL_MS    = 5.0     # Phase 2: inter-ping interval
STRESS_RATE_HZ      = 50.0    # Phase 3: injection rate
STRESS_DURATION_S   = 30.0    # Phase 3: duration
CONTINUOUS_WARMUP_S = 300.0   # Phase 6: seconds before rekey (5 min)
CONTINUOUS_MEASURE_S= 300.0   # Phase 6: seconds after rekey trigger (5 min)
CONTINUOUS_RATE_HZ  = 50.0    # Phase 6: packet rate


def _proxy_stop_seconds(
    hb_duration: float,
    ping_count: int,
    ping_interval_ms: float,
    stress_duration: float,
    continuous_warmup: float,
    continuous_measure: float,
) -> float:
    return (
        hb_duration + 10.0
        + (ping_count * ping_interval_ms / 1000.0) + 10.0
        + stress_duration + 10.0
        + continuous_warmup + continuous_measure + 30.0
        + 90.0  # startup + drain + phase teardown overhead
    )


# ── Aggregate report writers ───────────────────────────────────────────────────

def _write_mavlink_latency_md(out_dir: Path, results: List[Dict[str, Any]]) -> None:
    """mavlink-latency.md — aggregated RTT + stress latency across all AEADs."""
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "# MAVLink Tunnel — Latency Report",
        "",
        f"**Generated:** {ts}  ",
        f"**PING test:** 1000 pings at 5 ms interval per AEAD  ",
        f"**Stress test:** 50 Hz / 30 s per AEAD  ",
        "",
        "## PING RTT Distribution (μs)",
        "",
        "| AEAD | Delivery % | Mean | Median | P95 | P99 | Min | Max | Jitter Mean |",
        "|------|-----------|------|--------|-----|-----|-----|-----|-------------|",
    ]
    for r in results:
        aead = r["aead"]
        if r.get("unsupported"):
            lines.append(f"| {aead} | *unsupported* | — | — | — | — | — | — | — |")
            continue
        p = r.get("ping_rtt_burst", {})
        lines.append(
            f"| {aead}"
            f" | {p.get('delivery_pct', '—')}%"
            f" | {p.get('rtt_mean_us', '—')} μs"
            f" | {p.get('rtt_median_us', '—')} μs"
            f" | {p.get('rtt_p95_us', '—')} μs"
            f" | {p.get('rtt_p99_us', '—')} μs"
            f" | {p.get('rtt_min_us', '—')} μs"
            f" | {p.get('rtt_max_us', '—')} μs"
            f" | {p.get('jitter_mean_us', '—')} μs |"
        )
    lines += [
        "",
        "## High-Rate Stress Latency (50 Hz / 30 s)",
        "",
        "| AEAD | Delivery % | RTT Mean (μs) | RTT P95 (μs) | RTT Max (μs) | Throughput (kbps) |",
        "|------|-----------|--------------|-------------|-------------|------------------|",
    ]
    for r in results:
        aead = r["aead"]
        if r.get("unsupported"):
            lines.append(f"| {aead} | *unsupported* | — | — | — | — |")
            continue
        h = r.get("high_rate_stress", {})
        lines.append(
            f"| {aead}"
            f" | {h.get('delivery_pct', '—')}%"
            f" | {h.get('rtt_mean_us', '—')}"
            f" | {h.get('rtt_p95_us', '—')}"
            f" | {h.get('rtt_max_us', '—')}"
            f" | {h.get('throughput_kbps', '—')} |"
        )
    (out_dir / "mavlink-latency.md").write_text("\n".join(lines), encoding="utf-8")


def _write_heartbeat_stability_md(out_dir: Path, results: List[Dict[str, Any]]) -> None:
    """heartbeat-stability.md — aggregated 1 Hz heartbeat continuity across all AEADs."""
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "# MAVLink Heartbeat Stability",
        "",
        f"**Generated:** {ts}  ",
        f"**Test:** 1 Hz HEARTBEAT for 60 s per AEAD  ",
        "",
        "## Heartbeat Continuity by AEAD",
        "",
        "| AEAD | Sent | Received | Delivery % | RTT Mean (ms) | RTT P95 (ms) | Interval Stdev (ms) | Status |",
        "|------|------|----------|-----------|--------------|-------------|-------------------|--------|",
    ]
    for r in results:
        aead = r["aead"]
        if r.get("unsupported"):
            lines.append(f"| {aead} | — | — | *unsupported* | — | — | — | SKIP |")
            continue
        hb = r.get("heartbeat_continuity", {})
        d = hb.get("delivery_pct", 0)
        rtt = hb.get("rtt", {})
        status = "**PASS**" if d >= 99.0 else "**DEGRADED**" if d >= 95.0 else "**FAIL**"
        lines.append(
            f"| {aead}"
            f" | {hb.get('sent', 0)}"
            f" | {hb.get('received', 0)}"
            f" | {d}%"
            f" | {rtt.get('mean_ms', '—')}"
            f" | {rtt.get('p95_ms', '—')}"
            f" | {hb.get('interval_deviation_ms', '—')}"
            f" | {status} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "| Status | Criteria |",
        "|--------|----------|",
        "| **PASS** | ≥ 99% delivery with stable 1 Hz interval |",
        "| **DEGRADED** | ≥ 95% delivery |",
        "| **FAIL** | < 95% delivery — tunnel instability detected |",
    ]
    (out_dir / "heartbeat-stability.md").write_text("\n".join(lines), encoding="utf-8")


def _write_rekey_events_md(out_dir: Path, results: List[Dict[str, Any]]) -> None:
    """rekey-events.md — AEAD rekey event log for all AEADs."""
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "# AEAD Rekey Events",
        "",
        f"**Generated:** {ts}  ",
        f"**Test:** 10-minute continuous traffic, rekey triggered at T+300 s  ",
        f"**Traffic rate:** 50 Hz / 32 B payload  ",
        "",
        "## Rekey Event Summary",
        "",
        "| AEAD | Triggered | Rekey OK | Pre-Rekey Delivery | During-Rekey Delivery | Post-Rekey Delivery | AEAD Continuous |",
        "|------|-----------|----------|-------------------|----------------------|--------------------|----|",
    ]
    for r in results:
        aead = r["aead"]
        if r.get("unsupported"):
            lines.append(f"| {aead} | — | — | — | — | — | *unsupported* |")
            continue
        rky = r.get("rekey_continuity", {})
        triggered = "Yes" if rky.get("rekey_triggered") else "No"
        ok = "Yes" if rky.get("rekey_ok") else "No"
        pre_d = rky.get("pre_rekey", {}).get("delivery_pct", "—")
        dur_d = rky.get("during_rekey", {}).get("delivery_pct", "—")
        post_d = rky.get("post_rekey", {}).get("delivery_pct", "—")
        cont = rky.get("aead_continuous")
        cont_str = "**✓ YES**" if cont is True else "**✗ NO**" if cont is False else "N/A"
        lines.append(
            f"| {aead}"
            f" | {triggered}"
            f" | {ok}"
            f" | {pre_d}%"
            f" | {dur_d}%"
            f" | {post_d}%"
            f" | {cont_str} |"
        )
    lines += [
        "",
        "## Rekey Window Detail",
        "",
        "| AEAD | Pre Sent | Pre RX | During Sent | During RX | Post Sent | Post RX |",
        "|------|----------|--------|-------------|-----------|-----------|---------|",
    ]
    for r in results:
        aead = r["aead"]
        if r.get("unsupported"):
            lines.append(f"| {aead} | — | — | — | — | — | — |")
            continue
        rky = r.get("rekey_continuity", {})
        pre = rky.get("pre_rekey", {})
        dur = rky.get("during_rekey", {})
        post = rky.get("post_rekey", {})
        lines.append(
            f"| {aead}"
            f" | {pre.get('sent', 0)}"
            f" | {pre.get('received', 0)}"
            f" | {dur.get('sent', 0)}"
            f" | {dur.get('received', 0)}"
            f" | {post.get('sent', 0)}"
            f" | {post.get('received', 0)} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "> **AEAD Continuous = YES** means the data plane maintained ≥ 95% packet delivery",
        "> through the key-rotation window. Validates epoch-based replay protection and",
        "> atomic cipher swap at the PQC session layer (PROTOCOL_VERSION 1.0).",
        ">",
        "> The *During-Rekey* window is the 5-second interval immediately following the",
        "> TCP rekey command. Packets in this window traverse both old and new AEAD keys",
        "> depending on epoch assignment.",
    ]
    (out_dir / "rekey-events.md").write_text("\n".join(lines), encoding="utf-8")


def _write_link_quality_md(out_dir: Path, results: List[Dict[str, Any]]) -> None:
    """link-quality.md — overall link quality matrix for all AEADs."""
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "# MAVLink Link Quality Assessment",
        "",
        f"**Generated:** {ts}  ",
        f"**Protocol version:** 1.0 (frozen)  ",
        "",
        "## Link Quality Matrix",
        "",
        "| AEAD | HB Delivery | PING Delivery | PING P95 RTT (μs) | Stress Delivery | Rekey Continuous | Grade |",
        "|------|------------|---------------|------------------|-----------------|------------------|-------|",
    ]
    for r in results:
        aead = r["aead"]
        if r.get("unsupported"):
            lines.append(f"| {aead} | — | — | — | — | — | **SKIP** |")
            continue
        hb_d  = r.get("heartbeat_continuity", {}).get("delivery_pct", 0)
        ping_d = r.get("ping_rtt_burst", {}).get("delivery_pct", 0)
        ping_p95 = r.get("ping_rtt_burst", {}).get("rtt_p95_us", "—")
        stress_d = r.get("high_rate_stress", {}).get("delivery_pct", 0)
        cont  = r.get("rekey_continuity", {}).get("aead_continuous")
        all_ok    = hb_d >= 99.0 and ping_d >= 99.0 and stress_d >= 99.0 and cont is True
        mostly_ok = hb_d >= 95.0 and ping_d >= 95.0 and stress_d >= 95.0
        grade = "**A**" if all_ok else "**B**" if mostly_ok else "**C**"
        cont_str = "✓" if cont is True else "✗" if cont is False else "?"
        lines.append(
            f"| {aead}"
            f" | {hb_d}%"
            f" | {ping_d}%"
            f" | {ping_p95}"
            f" | {stress_d}%"
            f" | {cont_str}"
            f" | {grade} |"
        )
    lines += [
        "",
        "## Grading Criteria",
        "",
        "| Grade | Criteria |",
        "|-------|----------|",
        "| **A** | All delivery metrics ≥ 99% AND rekey-continuous |",
        "| **B** | All delivery metrics ≥ 95% |",
        "| **C** | Any delivery metric < 95% |",
        "",
        "## Connection Stability Summary",
        "",
    ]
    n_total = len(results)
    n_a = sum(
        1 for r in results
        if not r.get("unsupported")
        and r.get("heartbeat_continuity", {}).get("delivery_pct", 0) >= 99.0
        and r.get("ping_rtt_burst", {}).get("delivery_pct", 0) >= 99.0
        and r.get("high_rate_stress", {}).get("delivery_pct", 0) >= 99.0
        and r.get("rekey_continuity", {}).get("aead_continuous") is True
    )
    n_cont = sum(
        1 for r in results
        if not r.get("unsupported")
        and r.get("rekey_continuity", {}).get("aead_continuous") is True
    )
    n_ok = sum(1 for r in results if not r.get("unsupported"))
    lines += [
        f"- AEADs tested    : {n_ok} / {n_total}",
        f"- Grade A         : {n_a} / {n_ok}",
        f"- Rekey-continuous: {n_cont} / {n_ok}",
        f"- Stable operation: {'ALL PASS' if n_a == n_ok and n_ok > 0 else 'SEE MATRIX'}",
    ]
    (out_dir / "link-quality.md").write_text("\n".join(lines), encoding="utf-8")


def _write_all_aead_summary_md(
    out_dir: Path,
    results: List[Dict[str, Any]],
    suite_id: str,
    env: Dict[str, Any],
) -> None:
    lines = [
        "# MAVLink Tunnel Benchmark — All-AEAD Summary",
        "",
        f"**Date:** {env.get('timestamp_utc')}  ",
        f"**Host:** {env.get('hostname')}  ",
        f"**Platform:** {env.get('platform')}  ",
        f"**Suite:** {suite_id}  ",
        f"**Protocol version:** 1.0 (frozen)  ",
        "",
        "## Per-AEAD Quick Results",
        "",
        "| AEAD | HB % | PING Mean (μs) | PING P95 (μs) | Stress % | Rekey OK | Continuous |",
        "|------|------|---------------|--------------|----------|----------|------------|",
    ]
    for r in results:
        aead = r["aead"]
        if r.get("unsupported"):
            lines.append(f"| {aead} | *skip* | — | — | — | — | — |")
            continue
        hb_d   = r.get("heartbeat_continuity", {}).get("delivery_pct", "—")
        p_mean = r.get("ping_rtt_burst", {}).get("rtt_mean_us", "—")
        p_p95  = r.get("ping_rtt_burst", {}).get("rtt_p95_us", "—")
        s_d    = r.get("high_rate_stress", {}).get("delivery_pct", "—")
        rky_ok = "✓" if r.get("rekey_continuity", {}).get("rekey_ok") else "✗"
        cont   = r.get("rekey_continuity", {}).get("aead_continuous")
        cont_s = "✓ YES" if cont is True else "✗ NO" if cont is False else "N/A"
        lines.append(
            f"| {aead} | {hb_d}% | {p_mean} | {p_p95} | {s_d}% | {rky_ok} | {cont_s} |"
        )
    (out_dir / "all-aead-summary.md").write_text("\n".join(lines), encoding="utf-8")


# ── Per-AEAD benchmark runner ──────────────────────────────────────────────────

def run_single_aead(
    suite_id: str,
    aead_token: str,
    base_out: Path,
    *,
    hb_duration: float = HB_DURATION_S,
    hb_rate: float = HB_RATE_HZ,
    ping_count: int = PING_COUNT,
    ping_interval_ms: float = PING_INTERVAL_MS,
    stress_rate: float = STRESS_RATE_HZ,
    stress_duration: float = STRESS_DURATION_S,
    continuous_warmup: float = CONTINUOUS_WARMUP_S,
    continuous_measure: float = CONTINUOUS_MEASURE_S,
    continuous_rate: float = CONTINUOUS_RATE_HZ,
) -> Dict[str, Any]:
    """
    Run the complete benchmark protocol for one AEAD token.

    Phases executed:
      1. Heartbeat continuity (hb_duration s @ hb_rate Hz)
      2. PING RTT burst (ping_count pings)
      3. High-rate telemetry stress (stress_rate Hz / stress_duration s)
      6. Continuous 10-min run with TCP rekey at T+continuous_warmup

    Returns result dict, or {'aead': token, 'unsupported': True} on failure.
    """
    out_dir = base_out / aead_token
    out_dir.mkdir(parents=True, exist_ok=True)

    stop_s = _proxy_stop_seconds(
        hb_duration, ping_count, ping_interval_ms,
        stress_duration, continuous_warmup, continuous_measure,
    )

    print(f"\n{'═' * 60}", flush=True)
    print(f"  AEAD : {aead_token}", flush=True)
    print(f"  Suite: {suite_id}", flush=True)
    print(f"  Proxy lifetime: {stop_s:.0f}s  (~{stop_s/60:.1f} min)", flush=True)
    print(f"{'═' * 60}", flush=True)

    # Single proxy session covering all phases, TCP control enabled for rekey
    proxies = _mod._start_proxies(
        suite_id, aead_token, out_dir,
        stop_seconds=stop_s,
        enable_tcp_control=True,
    )
    if proxies is None:
        print(f"  [SKIP] {aead_token} — proxy startup failed (unsupported on this host)", flush=True)
        return {"aead": aead_token, "unsupported": True, "reason": "proxy_startup_failed"}

    echo = _mod.DroneEchoService()
    echo.start()
    time.sleep(0.5)

    # ── Phase 1: Heartbeat continuity ─────────────────────────────────────────
    print(f"\n  [Phase 1] Heartbeat continuity "
          f"({hb_duration:.0f}s @ {hb_rate:.0f}Hz)", flush=True)
    hb_result = _mod.run_heartbeat_continuity(
        duration_s=hb_duration,
        rate_hz=hb_rate,
    )
    print(
        f"    → {hb_result['received']}/{hb_result['sent']}"
        f"  ({hb_result['delivery_pct']:.1f}%)"
        f"  RTT mean {hb_result.get('rtt', {}).get('mean_ms', '—')} ms"
        f"  interval_stdev {hb_result.get('interval_deviation_ms', '—')} ms",
        flush=True,
    )
    _mod._write_heartbeat_md(out_dir, hb_result)

    # ── Phase 2: PING RTT burst ────────────────────────────────────────────────
    print(f"\n  [Phase 2] PING RTT burst "
          f"({ping_count} pings @ {ping_interval_ms:.0f}ms interval)", flush=True)
    ping_result = _mod.run_ping_rtt_burst(
        count=ping_count,
        burst_interval_ms=ping_interval_ms,
    )
    print(
        f"    → {ping_result['received']}/{ping_result['count']}"
        f"  ({ping_result['delivery_pct']:.1f}%)"
        f"  mean {ping_result.get('rtt_mean_us', '—')} µs"
        f"  P95 {ping_result.get('rtt_p95_us', '—')} µs"
        f"  jitter {ping_result.get('jitter_mean_us', '—')} µs",
        flush=True,
    )
    _mod._write_ping_rtt_md(out_dir, ping_result)

    # ── Phase 3: High-rate telemetry stress ───────────────────────────────────
    print(f"\n  [Phase 3] High-rate stress "
          f"({stress_rate:.0f}Hz / {stress_duration:.0f}s)", flush=True)
    hrs_result = _mod.run_high_rate_stress(
        rate_hz=stress_rate,
        duration_s=stress_duration,
        payload_bytes=64,
    )
    print(
        f"    → {hrs_result['received']}/{hrs_result['sent']}"
        f"  ({hrs_result['delivery_pct']:.1f}%)"
        f"  RTT mean {hrs_result.get('rtt_mean_us', '—')} µs"
        f"  {hrs_result.get('throughput_kbps', '—')} kbps",
        flush=True,
    )
    _mod._write_high_rate_md(out_dir, hrs_result)

    echo.stop()
    time.sleep(0.5)

    # ── Phase 6: Continuous 10-minute run with rekey ──────────────────────────
    total_continuous = continuous_warmup + continuous_measure
    print(
        f"\n  [Phase 6] Continuous {total_continuous/60:.0f}-min run"
        f" ({continuous_rate:.0f}Hz, rekey @T+{continuous_warmup:.0f}s)",
        flush=True,
    )
    rky_echo = _mod.DroneEchoService()
    rky_echo.start()
    time.sleep(0.5)

    rky_result = _mod.run_rekey_continuity(
        suite_id=suite_id,
        aead_token=aead_token,
        warmup_s=continuous_warmup,
        measure_s=continuous_measure,
        rate_hz=continuous_rate,
        payload_bytes=32,
    )
    rky_echo.stop()

    print(
        f"    → triggered={rky_result['rekey_triggered']}"
        f"  ok={rky_result['rekey_ok']}"
        f"  pre={rky_result.get('pre_rekey', {}).get('delivery_pct', '—')}%"
        f"  during={rky_result.get('during_rekey', {}).get('delivery_pct', '—')}%"
        f"  post={rky_result.get('post_rekey', {}).get('delivery_pct', '—')}%"
        f"  continuous={rky_result.get('aead_continuous')}",
        flush=True,
    )

    proxies.stop()
    time.sleep(2.0)

    # ── Per-AEAD reports ──────────────────────────────────────────────────────
    _mod._write_rekey_md(out_dir, rky_result)

    env_snap = _mod.collect_environment()
    _mod._write_summary_md(
        out_dir, env_snap, hb_result, ping_result, hrs_result, rky_result,
        suite_id, aead_token,
    )

    # Per-AEAD raw JSON
    (out_dir / "raw-results.json").write_text(
        json.dumps({
            "aead": aead_token,
            "suite_id": suite_id,
            "environment": env_snap,
            "heartbeat_continuity": hb_result,
            "ping_rtt_burst": ping_result,
            "high_rate_stress": hrs_result,
            "rekey_continuity": rky_result,
        }, indent=2, default=str),
        encoding="utf-8",
    )

    return {
        "aead": aead_token,
        "suite_id": suite_id,
        "unsupported": False,
        "heartbeat_continuity": hb_result,
        "ping_rtt_burst": ping_result,
        "high_rate_stress": hrs_result,
        "rekey_continuity": rky_result,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="MAVLink 8-AEAD benchmark — complete 10-minute protocol"
    )
    parser.add_argument(
        "--suite", default=DEFAULT_SUITE_ID,
        help=f"Suite override for all AEADs (default: per-AEAD level-matched suite)",
    )
    parser.add_argument(
        "--aead", nargs="+", default=[p[0] for p in AEAD_SUITE_PAIRS],
        metavar="TOKEN",
        help="AEAD tokens to test (default: all 8, each paired with its native suite level)",
    )
    parser.add_argument(
        "--output-dir", default=str(ROOT / "mavlink-benchmark-report"),
        help="Root output directory",
    )
    parser.add_argument(
        "--hb-duration", type=float, default=HB_DURATION_S,
        help=f"Heartbeat test duration (s) [default: {HB_DURATION_S}]",
    )
    parser.add_argument(
        "--ping-count", type=int, default=PING_COUNT,
        help=f"PING burst count [default: {PING_COUNT}]",
    )
    parser.add_argument(
        "--stress-duration", type=float, default=STRESS_DURATION_S,
        help=f"High-rate stress duration (s) [default: {STRESS_DURATION_S}]",
    )
    parser.add_argument(
        "--continuous-warmup", type=float, default=CONTINUOUS_WARMUP_S,
        help=f"Phase-6 warmup before rekey (s) [default: {CONTINUOUS_WARMUP_S}]",
    )
    parser.add_argument(
        "--continuous-measure", type=float, default=CONTINUOUS_MEASURE_S,
        help=f"Phase-6 post-rekey measurement window (s) [default: {CONTINUOUS_MEASURE_S}]",
    )
    args = parser.parse_args()

    suite_id = args.suite
    out_dir  = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    env = _mod.collect_environment()
    _mod._write_environment_md(out_dir, env)

    # Build the AEAD-suite pair list: use args.aead to filter if specified
    if args.aead != [p[0] for p in AEAD_SUITE_PAIRS]:
        # User specified custom tokens → pair each with the suite_id override
        pairs = [(tok, suite_id) for tok in args.aead]
    else:
        pairs = list(AEAD_SUITE_PAIRS)

    n = len(pairs)
    est_per_min = (
        args.hb_duration + 15
        + (args.ping_count * PING_INTERVAL_MS / 1000.0) + 10
        + args.stress_duration + 10
        + args.continuous_warmup + args.continuous_measure + 60
    ) / 60.0
    est_total_min = est_per_min * n

    sep = "═" * 64
    print(f"\n{sep}", flush=True)
    print(f"  MAVLink Benchmark Report — All-AEAD Protocol (v1.0)", flush=True)
    print(f"  AEAD–Suite pairs:", flush=True)
    for tok, sid in pairs:
        print(f"    {tok:<20} → {sid}", flush=True)
    print(f"  Output    : {out_dir}", flush=True)
    print(f"  Estimated : ~{est_total_min:.0f} min total  ({est_per_min:.1f} min/AEAD)", flush=True)
    print(f"{sep}", flush=True)

    results: List[Dict[str, Any]] = []
    for idx, (aead_token, aead_suite) in enumerate(pairs, 1):
        print(f"\n[AEAD {idx}/{n}] ── {aead_token} (suite: {aead_suite}) ──", flush=True)
        r = run_single_aead(
            suite_id=aead_suite,
            aead_token=aead_token,
            base_out=out_dir,
            hb_duration=args.hb_duration,
            ping_count=args.ping_count,
            stress_duration=args.stress_duration,
            continuous_warmup=args.continuous_warmup,
            continuous_measure=args.continuous_measure,
        )
        results.append(r)

        if r.get("unsupported"):
            print(f"  [SKIP] {aead_token} — unsupported on this host", flush=True)
        else:
            hb_d  = r["heartbeat_continuity"]["delivery_pct"]
            p_d   = r["ping_rtt_burst"]["delivery_pct"]
            s_d   = r["high_rate_stress"]["delivery_pct"]
            cont  = r["rekey_continuity"].get("aead_continuous")
            print(
                f"  [DONE] {aead_token}:"
                f"  HB={hb_d}%  PING={p_d}%  STRESS={s_d}%"
                f"  CONTINUOUS={cont}",
                flush=True,
            )

    # ── Write aggregate reports ────────────────────────────────────────────────
    print(f"\n{sep}", flush=True)
    print(f"  Writing aggregate reports …", flush=True)

    _write_mavlink_latency_md(out_dir, results)
    print(f"  → mavlink-latency.md", flush=True)

    _write_heartbeat_stability_md(out_dir, results)
    print(f"  → heartbeat-stability.md", flush=True)

    _write_rekey_events_md(out_dir, results)
    print(f"  → rekey-events.md", flush=True)

    _write_link_quality_md(out_dir, results)
    print(f"  → link-quality.md", flush=True)

    _write_all_aead_summary_md(out_dir, results, "multi-level", env)
    print(f"  → all-aead-summary.md", flush=True)

    # ── raw-mavlink-log.json ───────────────────────────────────────────────────
    raw_log = {
        "metadata": {
            "tool": "run_mavlink_benchmark",
            "version": "1.0.0",
            "protocol_version": "1.0",
            "suite_pairs": [(tok, sid) for tok, sid in pairs],
            "timestamp_utc": env.get("timestamp_utc"),
            "aead_tokens": [tok for tok, _ in pairs],
            "phases": ["heartbeat_continuity", "ping_rtt_burst",
                       "high_rate_stress", "rekey_continuity"],
        },
        "environment": env,
        "results": results,
    }
    (out_dir / "raw-mavlink-log.json").write_text(
        json.dumps(raw_log, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  → raw-mavlink-log.json", flush=True)

    # ── Final summary ──────────────────────────────────────────────────────────
    n_ok   = sum(1 for r in results if not r.get("unsupported"))
    n_cont = sum(
        1 for r in results
        if not r.get("unsupported")
        and r.get("rekey_continuity", {}).get("aead_continuous") is True
    )

    print(f"\n{sep}", flush=True)
    print(f"  COMPLETE", flush=True)
    print(f"  AEADs benchmarked : {n_ok} / {n}", flush=True)
    print(f"  Rekey-continuous  : {n_cont} / {n_ok}", flush=True)
    print(f"  Reports           : {out_dir}", flush=True)
    print(f"{sep}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
