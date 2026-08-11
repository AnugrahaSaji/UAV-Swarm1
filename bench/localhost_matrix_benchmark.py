#!/usr/bin/env python3
"""Run direct localhost end-to-end tunnel benchmarks across the full suite matrix."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.suites import (
    aead_profiles_by_nist_level,
    get_suite,
    list_suites,
    normalize_aead_token_for_level,
)


def _base_env(psk_hex: str | None) -> Dict[str, str]:
    env = os.environ.copy()
    env["DRONE_HOST"] = "127.0.0.1"
    env["GCS_HOST"] = "127.0.0.1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["DRONE_PSK"] = psk_hex or env.get("DRONE_PSK") or secrets.token_hex(32)
    return env


def _ensure_identity(suite_id: str, env: Dict[str, str]) -> Path:
    key_dir = ROOT / "tmp_suite_keys" / suite_id
    key_file = key_dir / "gcs_signing.key"
    pub_file = key_dir / "gcs_signing.pub"
    if key_file.exists() and pub_file.exists():
        return key_dir

    key_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "core.run_proxy",
        "init-identity",
        "--suite",
        suite_id,
        "--output-dir",
        str(key_dir),
    ]
    subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return key_dir


def _wait_for_running(status_path: Path, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if status_path.exists():
            try:
                data = json.loads(status_path.read_text(encoding="utf-8"))
            except Exception:
                time.sleep(0.05)
                continue
            if data.get("status") in {"handshake_ok", "running"}:
                return True
        time.sleep(0.05)
    return False


def _run_echo_service(duration_s: float) -> Tuple[threading.Thread, Dict[str, int]]:
    stats = {"echoed": 0, "resets": 0}

    def worker() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 47004))
        sock.settimeout(0.3)

        for _ in range(6):
            sock.sendto(b"bootstrap", ("127.0.0.1", 47003))
            time.sleep(0.05)

        end = time.time() + duration_s
        while time.time() < end:
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except ConnectionResetError:
                stats["resets"] += 1
                continue

            if data == b"bootstrap":
                continue

            sock.sendto(data, ("127.0.0.1", 47003))
            stats["echoed"] += 1

        sock.close()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread, stats


def _measure_rtt(packet_count: int) -> Dict[str, Any]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 47002))
    sock.settimeout(0.3)

    drain_end = time.time() + 1.0
    while time.time() < drain_end:
        try:
            sock.recvfrom(65535)
        except (socket.timeout, ConnectionResetError):
            pass

    rtts_us: List[float] = []
    resets = 0
    timeouts = 0

    for i in range(packet_count):
        payload = f"pkt-{i:03d}".encode("ascii")
        start = time.perf_counter_ns()
        sock.sendto(payload, ("127.0.0.1", 47001))
        matched = False
        deadline = time.time() + 0.8

        while time.time() < deadline:
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except ConnectionResetError:
                resets += 1
                continue

            if data == payload:
                rtts_us.append((time.perf_counter_ns() - start) / 1000.0)
                matched = True
                break

        if not matched:
            timeouts += 1
        time.sleep(0.015)

    sock.close()

    out: Dict[str, Any] = {
        "sent": packet_count,
        "received": len(rtts_us),
        "timeouts": timeouts,
        "resets": resets,
    }
    if rtts_us:
        ordered = sorted(rtts_us)

        def pct(pct_value: float) -> float:
            idx = min(
                len(ordered) - 1,
                max(0, round((pct_value / 100.0) * (len(ordered) - 1))),
            )
            return ordered[idx]

        out.update(
            {
                "rtt_mean_us": round(statistics.mean(rtts_us), 2),
                "rtt_median_us": round(statistics.median(rtts_us), 2),
                "rtt_p95_us": round(pct(95), 2),
                "rtt_max_us": round(max(rtts_us), 2),
            }
        )
    return out


def _terminate_process(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def benchmark_suite(
    suite_id: str,
    *,
    aead_token: str,
    output_dir: Path,
    env: Dict[str, str],
    gcs_stop_s: float,
    drone_stop_s: float,
    packet_count: int,
    handshake_timeout_s: float,
) -> Dict[str, Any]:
    suite = get_suite(suite_id)
    assert suite is not None
    tag = f"{suite_id}__{aead_token}".replace("-", "_")
    key_dir = _ensure_identity(suite_id, env)

    gcs_status = output_dir / f"{tag}_gcs_status.json"
    drone_status = output_dir / f"{tag}_drone_status.json"
    gcs_final = output_dir / f"{tag}_gcs_final.json"
    drone_final = output_dir / f"{tag}_drone_final.json"
    for path in (gcs_status, drone_status, gcs_final, drone_final):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    gcs_cmd = [
        sys.executable,
        "-m",
        "core.run_proxy",
        "gcs",
        "--suite",
        suite_id,
        "--gcs-secret-file",
        str(key_dir / "gcs_signing.key"),
        "--aead",
        aead_token,
        "--stop-seconds",
        str(gcs_stop_s),
        "--quiet",
        "--status-file",
        str(gcs_status),
        "--json-out",
        str(gcs_final),
    ]
    drone_cmd = [
        sys.executable,
        "-m",
        "core.run_proxy",
        "drone",
        "--suite",
        suite_id,
        "--peer-pubkey-file",
        str(key_dir / "gcs_signing.pub"),
        "--aead",
        aead_token,
        "--stop-seconds",
        str(drone_stop_s),
        "--quiet",
        "--status-file",
        str(drone_status),
        "--json-out",
        str(drone_final),
    ]

    gcs_proc = subprocess.Popen(
        gcs_cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(1.2)
    drone_proc = subprocess.Popen(
        drone_cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    record: Dict[str, Any] = {
        "suite": suite_id,
        "kem": suite["kem_name"],
        "sig": suite["sig_name"],
        "nist_level": suite["nist_level"],
        "aead_token": aead_token,
        "success": False,
    }

    try:
        if not _wait_for_running(gcs_status, handshake_timeout_s) or not _wait_for_running(
            drone_status, handshake_timeout_s
        ):
            record["error"] = "handshake_timeout"
            return record

        time.sleep(2.0)
        echo_thread, echo_stats = _run_echo_service(max(3.5, (packet_count * 0.08) + 1.5))
        time.sleep(0.7)
        rtt = _measure_rtt(packet_count)
        echo_thread.join(timeout=10.0)

        drone_proc.wait(timeout=max(20.0, drone_stop_s + 6.0))
        gcs_proc.wait(timeout=max(20.0, gcs_stop_s + 6.0))

        gcs_data = _load_json(gcs_final)
        drone_data = _load_json(drone_final)
        gcs_ctr = gcs_data.get("counters", {})
        drone_ctr = drone_data.get("counters", {})
        gcs_hs = gcs_ctr.get("handshake_metrics", {})
        drone_hs = drone_ctr.get("handshake_metrics", {})

        record.update(
            {
                "success": True,
                "gcs_handshake_ms": round(float(gcs_hs.get("rekey_ms", 0.0)), 4),
                "drone_handshake_ms": round(float(drone_hs.get("rekey_ms", 0.0)), 4),
                "gcs_aead_encrypt_ms": round(float(gcs_ctr.get("aead_encrypt_ms", 0.0)), 6),
                "gcs_aead_decrypt_ms": round(float(gcs_ctr.get("aead_decrypt_ms", 0.0)), 6),
                "drone_aead_encrypt_ms": round(float(drone_ctr.get("aead_encrypt_ms", 0.0)), 6),
                "drone_aead_decrypt_ms": round(float(drone_ctr.get("aead_decrypt_ms", 0.0)), 6),
                "gcs_enc_in": int(gcs_ctr.get("enc_in", 0)),
                "gcs_enc_out": int(gcs_ctr.get("enc_out", 0)),
                "drone_enc_in": int(drone_ctr.get("enc_in", 0)),
                "drone_enc_out": int(drone_ctr.get("enc_out", 0)),
                "gcs_drops": int(gcs_ctr.get("drops", 0)),
                "drone_drops": int(drone_ctr.get("drops", 0)),
                "echoed": int(echo_stats["echoed"]),
                "echo_resets": int(echo_stats["resets"]),
                **rtt,
            }
        )
        return record
    except Exception as exc:
        record["error"] = str(exc)
        return record
    finally:
        _terminate_process(drone_proc)
        _terminate_process(gcs_proc)


def _resolve_suite_aead_tokens(
    suite_id: str,
    *,
    include: List[str],
    exclude: List[str],
) -> List[str]:
    suite = get_suite(suite_id)
    level = str(suite.get("nist_level", "")).upper()
    if include:
        tokens: List[str] = []
        for token in include:
            try:
                tokens.append(normalize_aead_token_for_level(token, level))
            except ValueError:
                continue
    else:
        tokens = list(aead_profiles_by_nist_level(runtime_only=True).get(level, ()))

    if exclude:
        blocked = set()
        for token in exclude:
            try:
                blocked.add(normalize_aead_token_for_level(token, level))
            except ValueError:
                continue
        tokens = [token for token in tokens if token not in blocked]
    return list(dict.fromkeys(tokens))


def main() -> int:
    parser = argparse.ArgumentParser(description="Localhost full-matrix end-to-end tunnel benchmark")
    parser.add_argument("--suite", help="Benchmark only one suite ID")
    parser.add_argument("--aead", action="append", default=[], help="AEAD token to include (repeatable)")
    parser.add_argument("--exclude-aead", action="append", default=[], help="AEAD token to exclude (repeatable)")
    parser.add_argument("--psk-hex", help="Shared PSK hex for the benchmark run; generated if omitted")
    parser.add_argument("--packet-count", type=int, default=12, help="RTT packets per suite")
    parser.add_argument("--gcs-stop-seconds", type=float, default=16.0)
    parser.add_argument("--drone-stop-seconds", type=float, default=14.0)
    parser.add_argument("--handshake-timeout", type=float, default=10.0)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "logs" / "localhost_live_matrix"),
        help="Directory for JSON outputs",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _base_env(args.psk_hex)
    suite_ids = [args.suite] if args.suite else list(list_suites().keys())
    cases: List[Tuple[str, str]] = []
    for suite_id in suite_ids:
        for aead_token in _resolve_suite_aead_tokens(
            suite_id,
            include=args.aead,
            exclude=args.exclude_aead,
        ):
            cases.append((suite_id, aead_token))
    results: List[Dict[str, Any]] = []
    total = len(cases)
    current = 0

    for suite_id, aead_token in cases:
        current += 1
        result = benchmark_suite(
            suite_id,
            aead_token=aead_token,
            output_dir=output_dir,
            env=env,
            gcs_stop_s=args.gcs_stop_seconds,
            drone_stop_s=args.drone_stop_seconds,
            packet_count=args.packet_count,
            handshake_timeout_s=args.handshake_timeout,
        )
        results.append(result)
        status = "OK" if result.get("success") else f"FAIL ({result.get('error', 'unknown')})"
        print(f"[{current:02d}/{total:02d}] {suite_id} [{aead_token}]: {status}", flush=True)

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    success_count = sum(1 for item in results if item.get("success"))
    print(f"Wrote {summary_path}", flush=True)
    print(f"Success {success_count}/{len(results)}", flush=True)
    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
