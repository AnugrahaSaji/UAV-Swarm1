#!/usr/bin/env python3
"""
MAVLink End-to-End Tunnel Benchmark
=====================================

Aggressively benchmarks MAVLink quality through the PQC secure tunnel.
Tests: heartbeat continuity, PING RTT burst, high-rate telemetry stress,
and AEAD rekey continuity.

Architecture (localhost loopback):
  [GCS "app"]  →  port 47001  →  [GCS Proxy]  →  encrypted UDP  →  [Drone Proxy]  →  port 47004  →  [Drone "app"]
  [GCS "app"]  ←  port 47002  ←  [GCS Proxy]  ←  encrypted UDP  ←  [Drone Proxy]  ←  port 47003  ←  [Drone "app"]

Reports saved to: mav-bench/
  environment.md
  heartbeat-continuity.md
  ping-rtt-burst.md
  high-rate-stress.md
  rekey-continuity.md
  benchmark-summary.md
  raw-results.json

Usage:
  python tools/run_mav_tunnel_bench.py [--output-dir mav-bench]
  python tools/run_mav_tunnel_bench.py --suite cs-mlkem512-mldsa44 --aead aesgcm
  python tools/run_mav_tunnel_bench.py --mode drone   # run on Pi via SSH
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import socket
import statistics
import struct
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import CONFIG
from core.suites import DEFAULT_SUITE_ID, get_suite

# ── Port layout ────────────────────────────────────────────────────────────────
GCS_PLAIN_TX = int(CONFIG.get("GCS_PLAINTEXT_TX", 47001))   # we send here → GCS proxy
GCS_PLAIN_RX = int(CONFIG.get("GCS_PLAINTEXT_RX", 47002))   # we read here ← GCS proxy
DRONE_PLAIN_TX = int(CONFIG.get("DRONE_PLAINTEXT_TX", 47003))  # drone app sends to proxy
DRONE_PLAIN_RX = int(CONFIG.get("DRONE_PLAINTEXT_RX", 47004))  # drone app reads from proxy
GCS_CTRL_PORT = int(CONFIG.get("GCS_CONTROL_PORT", 48080))

# ── MAVLink building ───────────────────────────────────────────────────────────

try:
    from pymavlink import mavutil as _mavutil
    HAS_PYMAVLINK = True
except ImportError:
    _mavutil = None  # type: ignore
    HAS_PYMAVLINK = False


def _x25crc(data: bytes) -> int:
    """MAVLink X25 CRC."""
    crc = 0xFFFF
    for d in data:
        tmp = d ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = (crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)
    return crc & 0xFFFF


def _mav1_build(msg_id: int, payload: bytes, crc_extra: int, seq: int = 0,
                sysid: int = 1, compid: int = 1) -> bytes:
    """Build a MAVLink v1 packet."""
    header = bytes([0xFE, len(payload), seq & 0xFF, sysid, compid, msg_id])
    full = header + payload
    crc_seed = bytes([crc_extra])
    crc_val = _x25crc(full[1:] + crc_seed)
    return full + struct.pack("<H", crc_val)


# MAVLink message IDs and CRC extras
_MAVID_HEARTBEAT = 0
_MAVID_PING = 4
_CRC_HEARTBEAT = 50
_CRC_PING = 237


def build_heartbeat(seq: int = 0, sysid: int = 1, compid: int = 1) -> bytes:
    """Build MAVLink v1 HEARTBEAT (9 bytes payload)."""
    # custom_mode(4u) type(1u) autopilot(1u) base_mode(1u) system_status(1u) mavlink_version(1u)
    payload = struct.pack("<IBBBBB", 0, 6, 0, 0, 4, 3)
    return _mav1_build(_MAVID_HEARTBEAT, payload, _CRC_HEARTBEAT, seq, sysid, compid)


def build_ping(seq_id: int, time_usec: int, mav_seq: int = 0,
               sysid: int = 1, compid: int = 1) -> bytes:
    """Build MAVLink v1 PING (14 bytes payload). Uses time_usec as RTT timestamp."""
    # time_usec(8u) seq(4u) target_system(1u) target_component(1u)
    payload = struct.pack("<QIbb", time_usec, seq_id, 0, 0)
    return _mav1_build(_MAVID_PING, payload, _CRC_PING, mav_seq & 0xFF, sysid, compid)


def parse_ping_seq_usec(data: bytes) -> Optional[Tuple[int, int]]:
    """Extract (seq, time_usec) from a MAVLink v1 PING packet, or None if not a PING."""
    # Minimum: 6 (header) + 14 (payload) + 2 (crc) = 22 bytes
    if len(data) < 22:
        return None
    if data[0] != 0xFE:
        return None
    if data[5] != _MAVID_PING:
        return None
    try:
        t_usec, seq_id = struct.unpack_from("<QI", data, 6)
        return seq_id, t_usec
    except struct.error:
        return None


# ── Tunnel proxy management ────────────────────────────────────────────────────

DEFAULT_PSK = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"


def _ensure_identity(suite_id: str, env: Dict[str, str]) -> Path:
    key_dir = ROOT / "tmp_suite_keys" / suite_id
    if (key_dir / "gcs_signing.key").exists() and (key_dir / "gcs_signing.pub").exists():
        return key_dir
    key_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "core.run_proxy", "init-identity",
         "--suite", suite_id, "--output-dir", str(key_dir)],
        cwd=ROOT, env=env, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return key_dir


def _proxy_env(suite_id: str) -> Dict[str, str]:
    env = os.environ.copy()
    env["DRONE_HOST"] = "127.0.0.1"
    env["GCS_HOST"] = "127.0.0.1"
    env["TUNNEL_HOST_PROFILE"] = "localhost"
    env["PYTHONIOENCODING"] = "utf-8"
    env["DRONE_PSK"] = env.get("DRONE_PSK") or DEFAULT_PSK
    return env


def _wait_status(path: Path, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if path.exists():
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                time.sleep(0.05)
                continue
            if d.get("status") in {"handshake_ok", "running"}:
                return True
        time.sleep(0.05)
    return False


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


@dataclass
class Proxies:
    gcs: subprocess.Popen
    drone: subprocess.Popen
    gcs_status: Path
    drone_status: Path
    gcs_final: Path
    drone_final: Path

    def stop(self) -> None:
        _kill(self.gcs)
        _kill(self.drone)


def _start_proxies(
    suite_id: str,
    aead_token: str,
    out_dir: Path,
    *,
    stop_seconds: float = 180.0,
    enable_tcp_control: bool = False,
) -> Optional[Proxies]:
    env = _proxy_env(suite_id)
    key_dir = _ensure_identity(suite_id, env)
    tag = f"{suite_id}__{aead_token}".replace("-", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    gcs_status = out_dir / f"{tag}_gcs_status.json"
    drone_status = out_dir / f"{tag}_drone_status.json"
    gcs_final = out_dir / f"{tag}_gcs_final.json"
    drone_final = out_dir / f"{tag}_drone_final.json"
    for p in (gcs_status, drone_status, gcs_final, drone_final):
        p.unlink(missing_ok=True)

    gcs_cmd = [
        sys.executable, "-m", "core.run_proxy", "gcs",
        "--suite", suite_id,
        "--gcs-secret-file", str(key_dir / "gcs_signing.key"),
        "--aead", aead_token,
        "--stop-seconds", str(stop_seconds),
        "--quiet",
        "--status-file", str(gcs_status),
        "--json-out", str(gcs_final),
    ]
    if enable_tcp_control:
        gcs_cmd += ["--enable-tcp-control"]

    drone_cmd = [
        sys.executable, "-m", "core.run_proxy", "drone",
        "--suite", suite_id,
        "--peer-pubkey-file", str(key_dir / "gcs_signing.pub"),
        "--aead", aead_token,
        "--stop-seconds", str(stop_seconds),
        "--quiet",
        "--status-file", str(drone_status),
        "--json-out", str(drone_final),
    ]

    si = subprocess.STARTUPINFO() if sys.platform == "win32" else None
    if si:
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0

    gcs_proc = subprocess.Popen(
        gcs_cmd, env=env, cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        startupinfo=si,
    )
    time.sleep(1.2)  # give GCS TCP handshake port time to open
    drone_proc = subprocess.Popen(
        drone_cmd, env=env, cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        startupinfo=si,
    )

    if not _wait_status(gcs_status, 30.0):
        _kill(gcs_proc)
        _kill(drone_proc)
        return None
    if not _wait_status(drone_status, 30.0):
        _kill(gcs_proc)
        _kill(drone_proc)
        return None

    return Proxies(gcs_proc, drone_proc, gcs_status, drone_status, gcs_final, drone_final)


# ── Drone "app" echo service ───────────────────────────────────────────────────

class DroneEchoService:
    """Simulates the drone MAVLink application: receives on DRONE_PLAIN_RX, echoes on DRONE_PLAIN_TX."""

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.rx_count = 0
        self.tx_count = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", DRONE_PLAIN_RX))
        sock.settimeout(0.15)
        # Bootstrap: knock drone proxy so it latches our address
        for _ in range(8):
            try:
                sock.sendto(b"\x00" * 6, ("127.0.0.1", DRONE_PLAIN_TX))
            except Exception:
                pass
            time.sleep(0.05)
        while self._running:
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                continue
            if not data or data == b"\x00" * len(data):
                continue
            try:
                sock.sendto(data, ("127.0.0.1", DRONE_PLAIN_TX))
                with self._lock:
                    self.rx_count += 1
                    self.tx_count += 1
            except Exception:
                pass
        sock.close()


# ── Test phases ────────────────────────────────────────────────────────────────

def _pct(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, round(p / 100.0 * (len(s) - 1))))
    return s[idx]


def _stats_ms(samples_ms: List[float]) -> Dict[str, float]:
    if not samples_ms:
        return {"n": 0}
    return {
        "n": len(samples_ms),
        "mean_ms": round(statistics.mean(samples_ms), 3),
        "median_ms": round(statistics.median(samples_ms), 3),
        "p95_ms": round(_pct(samples_ms, 95), 3),
        "p99_ms": round(_pct(samples_ms, 99), 3),
        "min_ms": round(min(samples_ms), 3),
        "max_ms": round(max(samples_ms), 3),
        "stdev_ms": round(statistics.stdev(samples_ms), 3) if len(samples_ms) > 1 else 0.0,
    }


def run_heartbeat_continuity(
    duration_s: float = 60.0,
    rate_hz: float = 1.0,
    timeout_per_pkt_s: float = 2.5,
) -> Dict[str, Any]:
    """
    Phase 1: Send HEARTBEAT at rate_hz for duration_s.
    Measure: interval deviation, loss rate, delivery ratio.
    """
    print(f"  [HB] Heartbeat continuity: {rate_hz} Hz for {duration_s:.0f}s ...", flush=True)

    tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx_sock.bind(("127.0.0.1", GCS_PLAIN_RX))
    rx_sock.settimeout(0.05)

    # Drain stale
    t_drain = time.time() + 0.5
    while time.time() < t_drain:
        try:
            rx_sock.recvfrom(65535)
        except socket.timeout:
            break
        except ConnectionResetError:
            pass

    interval_s = 1.0 / rate_hz
    sent = 0
    received = 0
    timeouts = 0
    rtts_ms: List[float] = []
    intervals_ms: List[float] = []
    last_rx_mono = 0.0

    deadline = time.time() + duration_s
    seq = 0
    next_send = time.time()

    while time.time() < deadline:
        now = time.time()
        if now >= next_send:
            pkt = build_heartbeat(seq % 256)
            seq += 1
            tx_sock.sendto(pkt, ("127.0.0.1", GCS_PLAIN_TX))
            sent += 1
            send_ns = time.perf_counter_ns()
            next_send = now + interval_s

            # Wait for echo
            recv_deadline = time.time() + timeout_per_pkt_s
            got = False
            while time.time() < recv_deadline:
                try:
                    data, _ = rx_sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except ConnectionResetError:
                    continue
                if len(data) >= 6 and data[0] == 0xFE and data[5] == _MAVID_HEARTBEAT:
                    rtt_ms = (time.perf_counter_ns() - send_ns) / 1e6
                    rtts_ms.append(rtt_ms)
                    if last_rx_mono > 0:
                        intervals_ms.append((time.monotonic() - last_rx_mono) * 1000.0)
                    last_rx_mono = time.monotonic()
                    received += 1
                    got = True
                    break
            if not got:
                timeouts += 1
        else:
            time.sleep(max(0, next_send - time.time()) * 0.5)

    tx_sock.close()
    rx_sock.close()

    delivery_pct = (received / sent * 100.0) if sent > 0 else 0.0
    interval_deviation_ms = statistics.stdev(intervals_ms) if len(intervals_ms) > 1 else 0.0
    expected_interval_ms = 1000.0 / rate_hz
    interval_error_pct = (interval_deviation_ms / expected_interval_ms * 100.0) if expected_interval_ms > 0 else 0.0

    return {
        "phase": "heartbeat_continuity",
        "rate_hz": rate_hz,
        "duration_s": duration_s,
        "sent": sent,
        "received": received,
        "timeouts": timeouts,
        "delivery_pct": round(delivery_pct, 2),
        "rtt": _stats_ms(rtts_ms),
        "interval_target_ms": expected_interval_ms,
        "interval_deviation_ms": round(interval_deviation_ms, 3),
        "interval_error_pct": round(interval_error_pct, 2),
        "interval_samples": intervals_ms[:50],  # first 50 for raw analysis
    }


def run_ping_rtt_burst(
    count: int = 1000,
    burst_interval_ms: float = 5.0,
    timeout_s: float = 1.5,
) -> Dict[str, Any]:
    """
    Phase 2: Send 'count' PING messages with burst_interval_ms gap.
    Measure per-packet RTT (us resolution), jitter, loss.
    """
    print(f"  [PNG] PING RTT burst: {count} pings @ {burst_interval_ms:.1f}ms interval ...", flush=True)

    tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx_sock.bind(("127.0.0.1", GCS_PLAIN_RX))
    rx_sock.settimeout(0.02)

    t_drain = time.time() + 0.3
    while time.time() < t_drain:
        try:
            rx_sock.recvfrom(65535)
        except (socket.timeout, ConnectionResetError):
            pass

    rtts_us: List[float] = []
    jitters_us: List[float] = []
    timeouts = 0
    ooo = 0  # out-of-order
    last_rtt_us: Optional[float] = None
    send_times_ns: Dict[int, int] = {}

    interval_s = burst_interval_ms / 1000.0

    for seq_id in range(count):
        t_usec = int(time.perf_counter_ns() // 1000)
        pkt = build_ping(seq_id, t_usec, seq_id & 0xFF)
        send_ns = time.perf_counter_ns()
        send_times_ns[seq_id] = send_ns
        tx_sock.sendto(pkt, ("127.0.0.1", GCS_PLAIN_TX))

        # Receive response
        recv_dl = time.time() + timeout_s
        got = False
        while time.time() < recv_dl:
            try:
                data, _ = rx_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue
            parsed = parse_ping_seq_usec(data)
            if parsed is not None:
                r_seq, r_usec = parsed
                if r_seq in send_times_ns:
                    rtt_us = (time.perf_counter_ns() - send_times_ns[r_seq]) / 1000.0
                    rtts_us.append(rtt_us)
                    if last_rtt_us is not None:
                        jitters_us.append(abs(rtt_us - last_rtt_us))
                    last_rtt_us = rtt_us
                    if r_seq != seq_id:
                        ooo += 1
                    got = True
                    break
            elif data and len(data) > 6 and data[0] == 0xFE:
                # Non-PING response (echo of raw bytes) - use send time
                if seq_id in send_times_ns:
                    rtt_us = (time.perf_counter_ns() - send_times_ns[seq_id]) / 1000.0
                    rtts_us.append(rtt_us)
                    if last_rtt_us is not None:
                        jitters_us.append(abs(rtt_us - last_rtt_us))
                    last_rtt_us = rtt_us
                    got = True
                    break

        if not got:
            timeouts += 1

        if interval_s > 0:
            time.sleep(interval_s)

    tx_sock.close()
    rx_sock.close()

    received = len(rtts_us)
    delivery_pct = (received / count * 100.0) if count > 0 else 0.0

    result: Dict[str, Any] = {
        "phase": "ping_rtt_burst",
        "count": count,
        "burst_interval_ms": burst_interval_ms,
        "sent": count,
        "received": received,
        "timeouts": timeouts,
        "out_of_order": ooo,
        "delivery_pct": round(delivery_pct, 2),
        "rtt_us": _stats_ms([r / 1000.0 for r in rtts_us]),   # in ms for _stats_ms
        "jitter_us": _stats_ms([j / 1000.0 for j in jitters_us]),
    }
    # Re-express RTT in us directly for the report
    if rtts_us:
        result["rtt_mean_us"] = round(statistics.mean(rtts_us), 2)
        result["rtt_median_us"] = round(sorted(rtts_us)[len(rtts_us) // 2], 2)
        result["rtt_p95_us"] = round(_pct(rtts_us, 95), 2)
        result["rtt_p99_us"] = round(_pct(rtts_us, 99), 2)
        result["rtt_min_us"] = round(min(rtts_us), 2)
        result["rtt_max_us"] = round(max(rtts_us), 2)
        result["jitter_mean_us"] = round(statistics.mean(jitters_us), 2) if jitters_us else 0.0
        result["jitter_p95_us"] = round(_pct(jitters_us, 95), 2) if jitters_us else 0.0
    return result


def run_high_rate_stress(
    rate_hz: float = 50.0,
    duration_s: float = 30.0,
    payload_bytes: int = 64,
) -> Dict[str, Any]:
    """
    Phase 3: High-rate telemetry stress. Inject at rate_hz continuously.
    Measure delivery ratio and tunnel saturation.
    Uses raw probe packets (no MAVLink framing overhead at high rate).
    """
    print(f"  [HRS] High-rate stress: {rate_hz} Hz for {duration_s:.0f}s @ {payload_bytes}B ...", flush=True)

    tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx_sock.bind(("127.0.0.1", GCS_PLAIN_RX))
    rx_sock.settimeout(0.01)

    t_drain = time.time() + 0.2
    while time.time() < t_drain:
        try:
            rx_sock.recvfrom(65535)
        except (socket.timeout, ConnectionResetError):
            pass

    interval_s = 1.0 / rate_hz
    sent = 0
    received = 0
    timeouts = 0
    rtts_us: List[float] = []
    bytes_sent = 0
    bytes_rx = 0

    # Non-blocking rx collector thread
    rx_buf: List[Tuple[int, int]] = []  # (seq, recv_ns)
    rx_lock = threading.Lock()
    rx_running = True

    def _rx_worker() -> None:
        while rx_running:
            try:
                data, _ = rx_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                continue
            if len(data) >= 8:
                try:
                    seq_n, send_ns = struct.unpack_from("<IQ", data, 0)
                    recv_ns = time.perf_counter_ns()
                    with rx_lock:
                        rx_buf.append((seq_n, recv_ns - send_ns))
                except struct.error:
                    pass

    rx_thread = threading.Thread(target=_rx_worker, daemon=True)
    rx_thread.start()

    deadline = time.time() + duration_s
    seq = 0
    next_send = time.time()

    while time.time() < deadline:
        now = time.time()
        if now >= next_send:
            send_ns = time.perf_counter_ns()
            # Embed seq + send_ns in first 12 bytes
            prefix = struct.pack("<IQ", seq, send_ns)
            pad = bytes(max(0, payload_bytes - len(prefix)))
            pkt = prefix + pad
            try:
                tx_sock.sendto(pkt, ("127.0.0.1", GCS_PLAIN_TX))
                sent += 1
                bytes_sent += len(pkt)
                seq += 1
            except Exception:
                pass
            next_send += interval_s
        else:
            time.sleep(max(0, next_send - now) * 0.8)

    rx_running = False
    rx_thread.join(timeout=2.0)

    with rx_lock:
        buf = list(rx_buf)

    received = len(buf)
    if buf:
        rtts_us = [delta_ns / 1000.0 for _, delta_ns in buf]

    delivery_pct = (received / sent * 100.0) if sent > 0 else 0.0
    throughput_kbps = (bytes_sent * 8 / duration_s / 1000.0)

    result: Dict[str, Any] = {
        "phase": "high_rate_stress",
        "rate_hz": rate_hz,
        "duration_s": duration_s,
        "payload_bytes": payload_bytes,
        "sent": sent,
        "received": received,
        "delivery_pct": round(delivery_pct, 2),
        "throughput_kbps": round(throughput_kbps, 2),
    }
    if rtts_us:
        result["rtt_mean_us"] = round(statistics.mean(rtts_us), 2)
        result["rtt_p95_us"] = round(_pct(rtts_us, 95), 2)
        result["rtt_max_us"] = round(max(rtts_us), 2)
    return result


def _send_tcp_rekey(suite_id: str, aead_token: str, host: str = "127.0.0.1",
                    port: int = GCS_CTRL_PORT) -> Tuple[bool, str]:
    """Send TCP JSON rekey command to GCS control port."""
    cmd = {"cmd": "rekey", "suite": suite_id, "aead": aead_token}
    try:
        with socket.create_connection((host, port), timeout=5.0) as s:
            s.sendall(json.dumps(cmd).encode() + b"\n")
            s.settimeout(5.0)
            resp = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
                if b"\n" in resp:
                    break
        return True, resp.decode(errors="replace").strip()
    except Exception as exc:
        return False, str(exc)


def run_rekey_continuity(
    suite_id: str,
    aead_token: str,
    warmup_s: float = 10.0,
    measure_s: float = 60.0,
    post_rekey_s: float = 20.0,
    rate_hz: float = 50.0,
    payload_bytes: int = 32,
) -> Dict[str, Any]:
    """
    Phase 4: AEAD rekey continuity.
    Run continuous traffic, trigger rekey at warmup_s, measure delivery before/during/after.
    """
    print(f"  [RKY] Rekey continuity: {rate_hz} Hz traffic, trigger rekey at {warmup_s:.0f}s ...", flush=True)

    tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx_sock.bind(("127.0.0.1", GCS_PLAIN_RX))
    rx_sock.settimeout(0.01)

    t_drain = time.time() + 0.3
    while time.time() < t_drain:
        try:
            rx_sock.recvfrom(65535)
        except (socket.timeout, ConnectionResetError):
            pass

    interval_s = 1.0 / rate_hz
    total_duration = warmup_s + measure_s

    # Sliding window tracking: (seq, send_mono, phase)
    # phase: "pre_rekey", "during_rekey", "post_rekey"
    send_log: List[Dict[str, Any]] = []
    recv_seqs: set = set()
    recv_lock = threading.Lock()
    rx_run = True
    rekey_triggered_at: Optional[float] = None
    rekey_response: str = ""
    rekey_result = False

    def _rx_worker() -> None:
        while rx_run:
            try:
                data, _ = rx_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                continue
            if len(data) >= 8:
                try:
                    seq_n, _ = struct.unpack_from("<IQ", data, 0)
                    with recv_lock:
                        recv_seqs.add(seq_n)
                except struct.error:
                    pass

    rx_thread = threading.Thread(target=_rx_worker, daemon=True)
    rx_thread.start()

    deadline = time.time() + total_duration
    seq = 0
    next_send = time.time()
    rekey_done = False
    start_mono = time.monotonic()

    while time.time() < deadline:
        now = time.time()
        now_mono = time.monotonic()

        if now >= next_send:
            elapsed = now_mono - start_mono
            if elapsed < warmup_s:
                phase = "pre_rekey"
            elif elapsed < warmup_s + 5.0:
                phase = "during_rekey"
            else:
                phase = "post_rekey"

            send_ns = time.perf_counter_ns()
            prefix = struct.pack("<IQ", seq, send_ns)
            pad = bytes(max(0, payload_bytes - len(prefix)))
            pkt = prefix + pad
            try:
                tx_sock.sendto(pkt, ("127.0.0.1", GCS_PLAIN_TX))
                send_log.append({"seq": seq, "phase": phase, "send_mono": now_mono})
                seq += 1
            except Exception:
                pass
            next_send += interval_s

        # Trigger rekey at warmup_s
        if not rekey_done and (time.monotonic() - start_mono) >= warmup_s:
            rekey_triggered_at = time.monotonic()
            ok, resp = _send_tcp_rekey(suite_id, aead_token)
            rekey_result = ok
            rekey_response = resp
            rekey_done = True
            print(f"    → Rekey triggered: ok={ok}, resp={resp[:80]}", flush=True)

        time.sleep(max(0, next_send - time.time()) * 0.5)

    rx_run = False
    rx_thread.join(timeout=2.0)
    time.sleep(0.5)  # flush buffered packets

    with recv_lock:
        rx_set = set(recv_seqs)

    tx_sock.close()
    rx_sock.close()

    # Classify packets
    pre, during, post = [], [], []
    for entry in send_log:
        if entry["phase"] == "pre_rekey":
            pre.append(entry["seq"])
        elif entry["phase"] == "during_rekey":
            during.append(entry["seq"])
        else:
            post.append(entry["seq"])

    def _window_stats(seqs: List[int]) -> Dict[str, Any]:
        if not seqs:
            return {"sent": 0, "received": 0, "delivery_pct": 0.0}
        rx = sum(1 for s in seqs if s in rx_set)
        return {
            "sent": len(seqs),
            "received": rx,
            "delivery_pct": round(rx / len(seqs) * 100.0, 2),
        }

    return {
        "phase": "rekey_continuity",
        "suite_id": suite_id,
        "aead_token": aead_token,
        "rate_hz": rate_hz,
        "warmup_s": warmup_s,
        "total_duration_s": total_duration,
        "rekey_triggered": rekey_done,
        "rekey_ok": rekey_result,
        "rekey_response": rekey_response[:200],
        "pre_rekey": _window_stats(pre),
        "during_rekey": _window_stats(during),
        "post_rekey": _window_stats(post),
        "total": _window_stats(list(range(seq))),
        "aead_continuous": (
            _window_stats(during)["delivery_pct"] >= 95.0
            if during else None
        ),
    }


# ── Environment collection ─────────────────────────────────────────────────────

def collect_environment() -> Dict[str, Any]:
    env: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "pymavlink_available": HAS_PYMAVLINK,
    }

    # CPU info
    if sys.platform.startswith("linux"):
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text()
            for line in cpuinfo.splitlines():
                if "Model name" in line or "model name" in line:
                    env["cpu_model"] = line.split(":", 1)[1].strip()
                    break
                if "Model" in line and "Raspberry" in line:
                    env["cpu_model"] = line.split(":", 1)[1].strip()
                    break
        except Exception:
            pass
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                env["cpu_temp_c"] = round(int(f.read().strip()) / 1000.0, 1)
        except Exception:
            pass

    # Check oqs
    try:
        import oqs  # type: ignore
        env["oqs_available"] = True
        try:
            env["liboqs_version"] = oqs.oqs_version()
        except Exception:
            pass
    except ImportError:
        env["oqs_available"] = False

    return env


# ── Report writers ─────────────────────────────────────────────────────────────

def _write_environment_md(out_dir: Path, env: Dict[str, Any]) -> None:
    md = [
        "# MAVLink Tunnel Benchmark — Environment",
        "",
        f"**Date:** {env.get('timestamp_utc', 'n/a')}  ",
        f"**Host:** {env.get('hostname', 'n/a')}  ",
        f"**Platform:** {env.get('platform', 'n/a')}  ",
        f"**Python:** {env.get('python', 'n/a')}  ",
        f"**CPU Count:** {env.get('cpu_count', 'n/a')}  ",
        f"**CPU Model:** {env.get('cpu_model', 'n/a')}  ",
    ]
    if "cpu_temp_c" in env:
        md.append(f"**CPU Temp:** {env['cpu_temp_c']} °C  ")
    if "oqs_available" in env:
        md.append(f"**OQS:** {'yes' if env['oqs_available'] else 'no'}  ")
    if "liboqs_version" in env:
        md.append(f"**liboqs:** {env['liboqs_version']}  ")
    md.append(f"**pymavlink:** {'yes' if env.get('pymavlink_available') else 'no'}  ")
    (out_dir / "environment.md").write_text("\n".join(md), encoding="utf-8")


def _write_heartbeat_md(out_dir: Path, r: Dict[str, Any]) -> None:
    md = [
        "# MAVLink Heartbeat Continuity",
        "",
        f"**Rate:** {r.get('rate_hz', 1)} Hz  ",
        f"**Duration:** {r.get('duration_s')} s  ",
        f"**Sent / Received:** {r.get('sent')} / {r.get('received')}  ",
        f"**Delivery:** {r.get('delivery_pct')} %  ",
        f"**Timeouts:** {r.get('timeouts')}  ",
        "",
        "## RTT (ms)",
        "",
    ]
    rtt = r.get("rtt", {})
    if rtt.get("n", 0) > 0:
        md += [
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| N | {rtt['n']} |",
            f"| Mean | {rtt.get('mean_ms')} ms |",
            f"| Median | {rtt.get('median_ms')} ms |",
            f"| P95 | {rtt.get('p95_ms')} ms |",
            f"| Min | {rtt.get('min_ms')} ms |",
            f"| Max | {rtt.get('max_ms')} ms |",
            f"| Stdev | {rtt.get('stdev_ms')} ms |",
        ]
    md += [
        "",
        "## Interval Quality",
        "",
        f"**Target Interval:** {r.get('interval_target_ms')} ms  ",
        f"**Interval Stdev:** {r.get('interval_deviation_ms')} ms  ",
        f"**Interval Error:** {r.get('interval_error_pct')} %  ",
        "",
        f"*Link quality: {'PASS' if r.get('delivery_pct', 0) >= 99.0 else 'DEGRADED' if r.get('delivery_pct', 0) >= 95.0 else 'FAIL'}*",
    ]
    (out_dir / "heartbeat-continuity.md").write_text("\n".join(md), encoding="utf-8")


def _write_ping_rtt_md(out_dir: Path, r: Dict[str, Any]) -> None:
    md = [
        "# MAVLink PING RTT Burst",
        "",
        f"**Count:** {r.get('count')} pings  ",
        f"**Interval:** {r.get('burst_interval_ms')} ms  ",
        f"**Sent / Received:** {r.get('sent')} / {r.get('received')}  ",
        f"**Delivery:** {r.get('delivery_pct')} %  ",
        f"**Timeouts:** {r.get('timeouts')}  ",
        f"**Out-of-Order:** {r.get('out_of_order', 0)}  ",
        "",
        "## RTT Distribution (μs)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Mean | {r.get('rtt_mean_us', '-')} μs |",
        f"| Median | {r.get('rtt_median_us', '-')} μs |",
        f"| P95 | {r.get('rtt_p95_us', '-')} μs |",
        f"| P99 | {r.get('rtt_p99_us', '-')} μs |",
        f"| Min | {r.get('rtt_min_us', '-')} μs |",
        f"| Max | {r.get('rtt_max_us', '-')} μs |",
        "",
        "## Jitter (μs)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Mean Jitter | {r.get('jitter_mean_us', '-')} μs |",
        f"| P95 Jitter | {r.get('jitter_p95_us', '-')} μs |",
    ]
    (out_dir / "ping-rtt-burst.md").write_text("\n".join(md), encoding="utf-8")


def _write_high_rate_md(out_dir: Path, r: Dict[str, Any]) -> None:
    md = [
        "# High-Rate Telemetry Stress",
        "",
        f"**Rate:** {r.get('rate_hz')} Hz  ",
        f"**Duration:** {r.get('duration_s')} s  ",
        f"**Payload:** {r.get('payload_bytes')} bytes  ",
        f"**Sent / Received:** {r.get('sent')} / {r.get('received')}  ",
        f"**Delivery:** {r.get('delivery_pct')} %  ",
        f"**Throughput:** {r.get('throughput_kbps')} kbps  ",
        "",
        "## Latency under Load (μs)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Mean RTT | {r.get('rtt_mean_us', '-')} μs |",
        f"| P95 RTT | {r.get('rtt_p95_us', '-')} μs |",
        f"| Max RTT | {r.get('rtt_max_us', '-')} μs |",
    ]
    (out_dir / "high-rate-stress.md").write_text("\n".join(md), encoding="utf-8")


def _write_rekey_md(out_dir: Path, r: Dict[str, Any]) -> None:
    continuous = r.get("aead_continuous")
    md = [
        "# AEAD Rekey Continuity",
        "",
        f"**Suite:** {r.get('suite_id')}  ",
        f"**AEAD:** {r.get('aead_token')}  ",
        f"**Rate:** {r.get('rate_hz')} Hz  ",
        f"**Rekey Triggered:** {'Yes' if r.get('rekey_triggered') else 'No'}  ",
        f"**Rekey OK:** {'Yes' if r.get('rekey_ok') else 'No (TCP control may be disabled)'}  ",
        "",
        "## Delivery by Window",
        "",
        "| Window | Sent | Received | Delivery |",
        "|--------|------|----------|----------|",
    ]
    for wname in ("pre_rekey", "during_rekey", "post_rekey", "total"):
        w = r.get(wname, {})
        md.append(
            f"| {wname.replace('_', ' ').title()} | {w.get('sent', 0)} | {w.get('received', 0)} | {w.get('delivery_pct', 0):.1f}% |"
        )
    md += [
        "",
        f"**AEAD Continuous (≥95% delivery during rekey):** "
        f"{'✓ YES' if continuous is True else '✗ NO' if continuous is False else 'N/A (rekey not triggered)'}  ",
        "",
        "> A continuous result means the AEAD data plane maintains packet delivery through the",
        "> key rotation window. This validates the epoch-based replay replay protection and",
        "> atomic cipher swap implementation.",
    ]
    (out_dir / "rekey-continuity.md").write_text("\n".join(md), encoding="utf-8")


def _write_summary_md(
    out_dir: Path,
    env: Dict[str, Any],
    hb: Dict[str, Any],
    ping: Dict[str, Any],
    hrs: Dict[str, Any],
    rky: Dict[str, Any],
    suite_id: str,
    aead_token: str,
) -> None:
    md = [
        "# MAVLink Tunnel Benchmark — Summary",
        "",
        f"**Date:** {env.get('timestamp_utc')}  ",
        f"**Host:** {env.get('hostname')}  ",
        f"**Suite:** {suite_id}  ",
        f"**AEAD:** {aead_token}  ",
        "",
        "## Results at a Glance",
        "",
        "| Phase | Metric | Value |",
        "|-------|--------|-------|",
        f"| Heartbeat (1 Hz/60s) | Delivery | {hb.get('delivery_pct')}% |",
        f"| Heartbeat (1 Hz/60s) | RTT Mean | {hb.get('rtt', {}).get('mean_ms', '-')} ms |",
        f"| Heartbeat (1 Hz/60s) | Interval Stdev | {hb.get('interval_deviation_ms')} ms |",
        f"| PING Burst (1000 pings) | Delivery | {ping.get('delivery_pct')}% |",
        f"| PING Burst (1000 pings) | RTT Mean | {ping.get('rtt_mean_us', '-')} μs |",
        f"| PING Burst (1000 pings) | RTT P95 | {ping.get('rtt_p95_us', '-')} μs |",
        f"| PING Burst (1000 pings) | Jitter Mean | {ping.get('jitter_mean_us', '-')} μs |",
        f"| High-Rate (50 Hz/30s) | Delivery | {hrs.get('delivery_pct')}% |",
        f"| High-Rate (50 Hz/30s) | Throughput | {hrs.get('throughput_kbps')} kbps |",
        f"| Rekey Continuity | During-rekey delivery | {rky.get('during_rekey', {}).get('delivery_pct', 'N/A')}% |",
        f"| Rekey Continuity | AEAD Continuous | {'Yes' if rky.get('aead_continuous') else 'No' if rky.get('aead_continuous') is False else 'N/A'} |",
    ]
    (out_dir / "benchmark-summary.md").write_text("\n".join(md), encoding="utf-8")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="MAVLink end-to-end tunnel benchmark")
    parser.add_argument("--suite", default=DEFAULT_SUITE_ID,
                        help=f"Suite ID (default: {DEFAULT_SUITE_ID})")
    parser.add_argument("--aead", default="aesgcm",
                        help="AEAD token (default: aesgcm)")
    parser.add_argument("--output-dir", default=str(ROOT / "mav-bench"),
                        help="Output directory for reports")
    parser.add_argument("--hb-duration", type=float, default=60.0,
                        help="Heartbeat test duration (s)")
    parser.add_argument("--hb-rate", type=float, default=1.0,
                        help="Heartbeat rate (Hz)")
    parser.add_argument("--ping-count", type=int, default=1000,
                        help="PING burst count")
    parser.add_argument("--ping-interval-ms", type=float, default=5.0,
                        help="PING inter-packet interval (ms)")
    parser.add_argument("--stress-rate", type=float, default=50.0,
                        help="High-rate stress injection (Hz)")
    parser.add_argument("--stress-duration", type=float, default=30.0,
                        help="Stress test duration (s)")
    parser.add_argument("--rekey-warmup", type=float, default=10.0,
                        help="Seconds before triggering rekey (s)")
    parser.add_argument("--rekey-measure", type=float, default=40.0,
                        help="Total rekey test duration (s)")
    parser.add_argument("--rekey-rate", type=float, default=50.0,
                        help="Packet rate during rekey test (Hz)")
    parser.add_argument("--skip-rekey", action="store_true",
                        help="Skip AEAD rekey continuity test")
    parser.add_argument("--handshake-timeout", type=float, default=45.0,
                        help="Proxy handshake timeout (s)")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    suite_id = args.suite
    aead_token = args.aead

    print(f"\n=== MAVLink Tunnel Benchmark ===", flush=True)
    print(f"    Suite   : {suite_id}", flush=True)
    print(f"    AEAD    : {aead_token}", flush=True)
    print(f"    Output  : {out_dir}", flush=True)
    print(f"    pymavlink: {'yes' if HAS_PYMAVLINK else 'no (using raw MAVLink bytes)'}", flush=True)
    print(f"", flush=True)

    # ── Collect environment ────────────────────────────────────────────────────
    env = collect_environment()
    _write_environment_md(out_dir, env)
    print(f"  [ENV] Host: {env['hostname']} | Python: {env['python']}", flush=True)

    total_proxy_time = (
        args.hb_duration + 10.0             # heartbeat
        + (args.ping_count * args.ping_interval_ms / 1000.0) + 10.0  # ping burst
        + args.stress_duration + 8.0        # stress
        + (args.rekey_measure + 15.0 if not args.skip_rekey else 0.0)  # rekey
        + 30.0                               # overhead
    )

    # ── Phase 1: Heartbeat continuity ─────────────────────────────────────────
    print(f"\n[Phase 1/4] Heartbeat Continuity", flush=True)
    proxies = _start_proxies(suite_id, aead_token, out_dir,
                             stop_seconds=total_proxy_time)
    if proxies is None:
        print("  ERROR: Proxy startup failed (handshake timeout). Check tunnel setup.", flush=True)
        return 1

    echo = DroneEchoService()
    echo.start()
    time.sleep(0.5)  # let echo service warm up

    hb_result = run_heartbeat_continuity(
        duration_s=args.hb_duration,
        rate_hz=args.hb_rate,
    )
    print(f"  → HB: {hb_result['received']}/{hb_result['sent']} ({hb_result['delivery_pct']:.1f}%)"
          f"  RTT mean {hb_result.get('rtt', {}).get('mean_ms', '-')} ms", flush=True)
    _write_heartbeat_md(out_dir, hb_result)

    # ── Phase 2: PING RTT burst ────────────────────────────────────────────────
    print(f"\n[Phase 2/4] PING RTT Burst", flush=True)
    ping_result = run_ping_rtt_burst(
        count=args.ping_count,
        burst_interval_ms=args.ping_interval_ms,
    )
    print(f"  → PING: {ping_result['received']}/{ping_result['count']} ({ping_result['delivery_pct']:.1f}%)"
          f"  RTT mean {ping_result.get('rtt_mean_us', '-')} µs"
          f"  P95 {ping_result.get('rtt_p95_us', '-')} µs"
          f"  jitter {ping_result.get('jitter_mean_us', '-')} µs",
          flush=True)
    _write_ping_rtt_md(out_dir, ping_result)

    # ── Phase 3: High-rate stress ──────────────────────────────────────────────
    print(f"\n[Phase 3/4] High-Rate Telemetry Stress ({args.stress_rate} Hz)", flush=True)
    hrs_result = run_high_rate_stress(
        rate_hz=args.stress_rate,
        duration_s=args.stress_duration,
        payload_bytes=64,
    )
    print(f"  → Stress: {hrs_result['received']}/{hrs_result['sent']} ({hrs_result['delivery_pct']:.1f}%)"
          f"  RTT mean {hrs_result.get('rtt_mean_us', '-')} µs"
          f"  {hrs_result.get('throughput_kbps')} kbps",
          flush=True)
    _write_high_rate_md(out_dir, hrs_result)

    echo.stop()
    proxies.stop()
    time.sleep(1.0)

    # ── Phase 4: AEAD rekey continuity ────────────────────────────────────────
    if args.skip_rekey:
        print(f"\n[Phase 4/4] AEAD Rekey Continuity — SKIPPED", flush=True)
        rky_result = {
            "phase": "rekey_continuity",
            "suite_id": suite_id,
            "aead_token": aead_token,
            "skipped": True,
            "rekey_triggered": False,
            "rekey_ok": False,
            "aead_continuous": None,
            "pre_rekey": {}, "during_rekey": {}, "post_rekey": {}, "total": {}
        }
    else:
        print(f"\n[Phase 4/4] AEAD Rekey Continuity", flush=True)
        rekey_proxy_time = args.rekey_measure + 25.0
        rkey_proxies = _start_proxies(
            suite_id, aead_token, out_dir,
            stop_seconds=rekey_proxy_time,
            enable_tcp_control=True,
        )
        if rkey_proxies is None:
            print("  WARNING: Rekey test proxy startup failed — skipping rekey test", flush=True)
            rky_result = {
                "phase": "rekey_continuity", "suite_id": suite_id, "aead_token": aead_token,
                "skipped": True, "rekey_triggered": False, "rekey_ok": False,
                "aead_continuous": None,
                "pre_rekey": {}, "during_rekey": {}, "post_rekey": {}, "total": {}
            }
        else:
            rky_echo = DroneEchoService()
            rky_echo.start()
            time.sleep(0.5)

            rky_result = run_rekey_continuity(
                suite_id=suite_id,
                aead_token=aead_token,
                warmup_s=args.rekey_warmup,
                measure_s=args.rekey_measure,
                rate_hz=args.rekey_rate,
                payload_bytes=32,
            )
            rky_echo.stop()
            rkey_proxies.stop()

            print(
                f"  → Rekey: triggered={rky_result['rekey_triggered']}"
                f"  ok={rky_result['rekey_ok']}"
                f"  during_delivery={rky_result.get('during_rekey', {}).get('delivery_pct', 'N/A')}%"
                f"  continuous={rky_result.get('aead_continuous')}",
                flush=True
            )

    _write_rekey_md(out_dir, rky_result)

    # ── Summary ────────────────────────────────────────────────────────────────
    _write_summary_md(out_dir, env, hb_result, ping_result, hrs_result, rky_result,
                      suite_id, aead_token)

    # ── Raw JSON ───────────────────────────────────────────────────────────────
    raw = {
        "metadata": {
            "tool": "run_mav_tunnel_bench",
            "version": "1.0.0",
            "suite_id": suite_id,
            "aead_token": aead_token,
            "timestamp_utc": env["timestamp_utc"],
        },
        "environment": env,
        "heartbeat_continuity": hb_result,
        "ping_rtt_burst": ping_result,
        "high_rate_stress": hrs_result,
        "rekey_continuity": rky_result,
    }
    (out_dir / "raw-results.json").write_text(
        json.dumps(raw, indent=2, default=str), encoding="utf-8"
    )

    print(f"\n=== Benchmark Complete ===", flush=True)
    print(f"  Reports saved to: {out_dir}", flush=True)
    print(f"  HB delivery:      {hb_result['delivery_pct']:.1f}%", flush=True)
    print(f"  PING RTT mean:    {ping_result.get('rtt_mean_us', '-')} µs", flush=True)
    print(f"  PING RTT P95:     {ping_result.get('rtt_p95_us', '-')} µs", flush=True)
    print(f"  Stress delivery:  {hrs_result['delivery_pct']:.1f}%", flush=True)
    print(f"  AEAD continuous:  {rky_result.get('aead_continuous')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
