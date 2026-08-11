#!/usr/bin/env python3
"""GCS-side benchmark campaign runner for frozen core experiments.

Outputs markdown reports to gcs-e2e-report/:
- environment.md
- kem-bench.md
- signature-bench.md
- aead-bench.md
- e2e-localhost.md
- benchmark-summary.md
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import ssl
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench.benchmark_pqc import get_oqs_kem_class, get_oqs_sig_class  # type: ignore
from bench.localhost_matrix_benchmark import benchmark_suite, _base_env  # type: ignore
from core.aead import AeadIds, Receiver, Sender, required_key_length_for_aead
from core.config import CONFIG
from core.suites import DEFAULT_SUITE_ID, get_suite

try:
    from core.suites import normalize_aead_token_for_level as _normalize_aead_token_for_level
except Exception:
    _normalize_aead_token_for_level = None


DEFAULT_OUT_DIR = ROOT / "gcs-e2e-report"
DEFAULT_WARMUP = 20
DEFAULT_ITERS = 200
AEAD_PAYLOADS = (64, 256, 1024, 4096)
KEM_ALGS = ("ML-KEM-512", "ML-KEM-768", "ML-KEM-1024")
SIG_ALGS = ("ML-DSA-44", "ML-DSA-65", "ML-DSA-87", "SPHINCS+-SHA2-128s-simple")
AEAD_TOKENS = (
    "aesgcm128",
    "aesgcm192",
    "aesgcm256",
    "aesccm128",
    "aesccm192",
    "aesccm256",
    "chacha20poly1305",
    "ascon128",
    "ascon128a",
)


@dataclass
class TimeStats:
    mean_ns: float
    median_ns: float
    p95_ns: float
    min_ns: int
    max_ns: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _p95(values: Sequence[int]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    idx = int(round(0.95 * (len(ordered) - 1)))
    return float(ordered[max(0, min(idx, len(ordered) - 1))])


def _stats(values: Sequence[int]) -> TimeStats:
    return TimeStats(
        mean_ns=statistics.mean(values),
        median_ns=statistics.median(values),
        p95_ns=_p95(values),
        min_ns=min(values),
        max_ns=max(values),
    )


def _to_us(ns: float) -> float:
    return ns / 1000.0


def _run_cmd(args: List[str]) -> str:
    try:
        proc = subprocess.run(args, check=False, capture_output=True, text=True)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if out:
            return out
        if err:
            return err
    except Exception:
        pass
    return "n/a"


def _cpu_info() -> Dict[str, str]:
    info = {
        "cpu_model": platform.processor() or "n/a",
        "cpu_max_clock": "n/a",
    }
    if os.name == "nt":
        out = _run_cmd(["wmic", "cpu", "get", "Name,MaxClockSpeed", "/value"])
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Name="):
                info["cpu_model"] = line.split("=", 1)[1].strip() or info["cpu_model"]
            elif line.startswith("MaxClockSpeed="):
                mhz = line.split("=", 1)[1].strip()
                if mhz:
                    info["cpu_max_clock"] = f"{mhz} MHz"
    return info


def _ram_info() -> str:
    if os.name != "nt":
        return "n/a"
    out = _run_cmd(["wmic", "computersystem", "get", "TotalPhysicalMemory", "/value"])
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("TotalPhysicalMemory="):
            raw = line.split("=", 1)[1].strip()
            if raw.isdigit():
                gib = int(raw) / (1024 ** 3)
                return f"{gib:.2f} GiB"
    return "n/a"


def _oqs_versions() -> Dict[str, str]:
    data = {
        "oqs_python": "unknown",
        "liboqs": "unknown",
    }
    try:
        import oqs  # type: ignore

        data["oqs_python"] = getattr(oqs, "__version__", "unknown")
        for attr in ("oqs_version", "OQS_VERSION", "liboqs_version"):
            value = getattr(oqs, attr, None)
            if value is None:
                continue
            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue
            data["liboqs"] = str(value)
            break
    except Exception:
        pass
    return data


def collect_environment() -> Dict[str, str]:
    cpu = _cpu_info()
    oqs_versions = _oqs_versions()
    return {
        "timestamp_utc": _utc_now(),
        "hostname": platform.node() or "n/a",
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": sys.version.replace("\n", " "),
        "openssl": ssl.OPENSSL_VERSION,
        "cpu_model": cpu["cpu_model"],
        "cpu_max_clock": cpu["cpu_max_clock"],
        "ram": _ram_info(),
        "oqs_python": oqs_versions["oqs_python"],
        "liboqs": oqs_versions["liboqs"],
    }


def benchmark_kem(iterations: int, warmup: int) -> List[Dict[str, Any]]:
    kem_cls = get_oqs_kem_class()
    rows: List[Dict[str, Any]] = []

    for alg in KEM_ALGS:
        keygen_ns: List[int] = []
        encap_ns: List[int] = []
        decap_ns: List[int] = []
        sample_sizes: Dict[str, int] = {}

        for i in range(warmup + iterations):
            with kem_cls(alg) as receiver:
                t0 = time.perf_counter_ns()
                public_key = receiver.generate_keypair()
                t1 = time.perf_counter_ns()

                with kem_cls(alg) as sender:
                    t2 = time.perf_counter_ns()
                    ciphertext, ss_sender = sender.encap_secret(public_key)
                    t3 = time.perf_counter_ns()

                t4 = time.perf_counter_ns()
                ss_receiver = receiver.decap_secret(ciphertext)
                t5 = time.perf_counter_ns()

                if ss_sender != ss_receiver:
                    raise RuntimeError(f"KEM correctness failed for {alg} at iteration {i}")

                if i == 0:
                    sample_sizes["public_key_bytes"] = len(public_key)
                    sample_sizes["ciphertext_bytes"] = len(ciphertext)
                    sample_sizes["shared_secret_bytes"] = len(ss_sender)

                if i >= warmup:
                    keygen_ns.append(t1 - t0)
                    encap_ns.append(t3 - t2)
                    decap_ns.append(t5 - t4)

        rows.append(
            {
                "algorithm": alg,
                "iterations": iterations,
                "warmup": warmup,
                "keygen": _stats(keygen_ns),
                "encap": _stats(encap_ns),
                "decap": _stats(decap_ns),
                **sample_sizes,
            }
        )

    return rows


def benchmark_signature(iterations: int, warmup: int) -> List[Dict[str, Any]]:
    sig_cls = get_oqs_sig_class()
    rows: List[Dict[str, Any]] = []
    message = b"secure-tunnel-gcs-signature-benchmark"

    for alg in SIG_ALGS:
        keygen_ns: List[int] = []
        sign_ns: List[int] = []
        verify_ns: List[int] = []
        sample_sizes: Dict[str, int] = {}

        for i in range(warmup + iterations):
            with sig_cls(alg) as signer:
                t0 = time.perf_counter_ns()
                public_key = signer.generate_keypair()
                t1 = time.perf_counter_ns()

                t2 = time.perf_counter_ns()
                signature = signer.sign(message)
                t3 = time.perf_counter_ns()

                t4 = time.perf_counter_ns()
                verify_ok = signer.verify(message, signature, public_key)
                t5 = time.perf_counter_ns()

                if not verify_ok:
                    raise RuntimeError(f"Signature correctness failed for {alg} at iteration {i}")

                if i == 0:
                    sample_sizes["public_key_bytes"] = len(public_key)
                    sample_sizes["signature_bytes"] = len(signature)

                if i >= warmup:
                    keygen_ns.append(t1 - t0)
                    sign_ns.append(t3 - t2)
                    verify_ns.append(t5 - t4)

        rows.append(
            {
                "algorithm": alg,
                "iterations": iterations,
                "warmup": warmup,
                "keygen": _stats(keygen_ns),
                "sign": _stats(sign_ns),
                "verify": _stats(verify_ns),
                **sample_sizes,
            }
        )

    return rows


def _suite_ids() -> AeadIds:
    suite = get_suite(DEFAULT_SUITE_ID)
    if suite is None:
        raise RuntimeError(f"Default suite not found: {DEFAULT_SUITE_ID}")
    return AeadIds(
        kem_id=int(suite["kem_id"]),
        kem_param=int(suite["kem_param_id"]),
        sig_id=int(suite["sig_id"]),
        sig_param=int(suite["sig_param_id"]),
    )


def benchmark_aead(iterations: int, warmup: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    ids = _suite_ids()
    session_id = secrets.token_bytes(int(CONFIG.get("WIRE_SESSION_ID_LEN", 16)))

    for token in AEAD_TOKENS:
        sender = None
        receiver = None
        try:
            try:
                key_len = required_key_length_for_aead(token)
            except Exception as exc:
                rows.append(
                    {
                        "algorithm": token,
                        "payload_bytes": -1,
                        "iterations": iterations,
                        "warmup": warmup,
                        "error": f"unsupported_on_host: {exc}",
                    }
                )
                continue
            key = secrets.token_bytes(key_len)
            sender = Sender(
                version=int(CONFIG["WIRE_VERSION"]),
                ids=ids,
                session_id=session_id,
                epoch=1,
                key_send=key,
                aead_token=token,
            )
            receiver = Receiver(
                version=int(CONFIG["WIRE_VERSION"]),
                ids=ids,
                session_id=session_id,
                epoch=1,
                key_recv=key,
                window=4096,
                strict_mode=True,
                aead_token=token,
            )

            for payload_size in AEAD_PAYLOADS:
                payload = secrets.token_bytes(payload_size)
                enc_ns: List[int] = []
                dec_ns: List[int] = []

                for i in range(warmup + iterations):
                    t0 = time.perf_counter_ns()
                    wire = sender.encrypt(payload)
                    t1 = time.perf_counter_ns()
                    out = receiver.decrypt(wire)
                    t2 = time.perf_counter_ns()

                    if out != payload:
                        raise RuntimeError(
                            f"AEAD correctness failed for {token} size {payload_size} at iteration {i}"
                        )

                    if i >= warmup:
                        enc_ns.append(t1 - t0)
                        dec_ns.append(t2 - t1)

                rows.append(
                    {
                        "algorithm": token,
                        "payload_bytes": payload_size,
                        "iterations": iterations,
                        "warmup": warmup,
                        "encrypt": _stats(enc_ns),
                        "decrypt": _stats(dec_ns),
                    }
                )
        except Exception as exc:
            if "ascon" in token.lower():
                rows.append(
                    {
                        "algorithm": token,
                        "payload_bytes": -1,
                        "iterations": iterations,
                        "warmup": warmup,
                        "error": f"ignored_ascon_issue: {exc}",
                    }
                )
            else:
                raise
        finally:
            if sender is not None:
                sender.destroy()
            if receiver is not None:
                receiver.destroy()

    return rows


def benchmark_e2e(output_dir: Path, packet_count: int) -> Dict[str, Any]:
    env = _base_env(None)
    suite = DEFAULT_SUITE_ID
    aead_token = "aesgcm"
    result = benchmark_suite(
        suite,
        aead_token=aead_token,
        output_dir=output_dir,
        env=env,
        gcs_stop_s=max(40.0, packet_count * 0.04),
        drone_stop_s=max(38.0, packet_count * 0.04),
        packet_count=packet_count,
        handshake_timeout_s=90.0,
    )
    return result


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def write_environment_md(path: Path, env: Dict[str, str]) -> None:
    rows = [[k, str(v)] for k, v in env.items()]
    content = "\n".join(
        [
            "# GCS Benchmark Environment",
            "",
            _md_table(["Field", "Value"], rows),
            "",
            "Method: values collected on benchmark host before measurements.",
        ]
    )
    path.write_text(content + "\n", encoding="utf-8")


def write_kem_md(path: Path, rows: List[Dict[str, Any]]) -> None:
    table_rows: List[List[str]] = []
    for row in rows:
        kg = row["keygen"]
        ec = row["encap"]
        dc = row["decap"]
        table_rows.append(
            [
                row["algorithm"],
                str(row["public_key_bytes"]),
                str(row["ciphertext_bytes"]),
                str(row["shared_secret_bytes"]),
                f"{_to_us(kg.mean_ns):.2f}",
                f"{_to_us(ec.mean_ns):.2f}",
                f"{_to_us(dc.mean_ns):.2f}",
                f"{_to_us(kg.p95_ns):.2f}",
                f"{_to_us(ec.p95_ns):.2f}",
                f"{_to_us(dc.p95_ns):.2f}",
            ]
        )

    content = "\n".join(
        [
            "# KEM Benchmark",
            "",
            "Correctness: each encapsulated shared secret matched decapsulation output.",
            "Time source: time.perf_counter_ns().",
            "",
            _md_table(
                [
                    "Algorithm",
                    "PK (B)",
                    "CT (B)",
                    "SS (B)",
                    "KeyGen mean (us)",
                    "Encap mean (us)",
                    "Decap mean (us)",
                    "KeyGen p95 (us)",
                    "Encap p95 (us)",
                    "Decap p95 (us)",
                ],
                table_rows,
            ),
        ]
    )
    path.write_text(content + "\n", encoding="utf-8")


def write_signature_md(path: Path, rows: List[Dict[str, Any]]) -> None:
    table_rows: List[List[str]] = []
    for row in rows:
        kg = row["keygen"]
        sg = row["sign"]
        vf = row["verify"]
        table_rows.append(
            [
                row["algorithm"],
                str(row["public_key_bytes"]),
                str(row["signature_bytes"]),
                f"{_to_us(kg.mean_ns):.2f}",
                f"{_to_us(sg.mean_ns):.2f}",
                f"{_to_us(vf.mean_ns):.2f}",
                f"{_to_us(kg.p95_ns):.2f}",
                f"{_to_us(sg.p95_ns):.2f}",
                f"{_to_us(vf.p95_ns):.2f}",
            ]
        )

    content = "\n".join(
        [
            "# Signature Benchmark",
            "",
            "Correctness: each signature verified successfully with generated public key.",
            "Time source: time.perf_counter_ns().",
            "",
            _md_table(
                [
                    "Algorithm",
                    "PK (B)",
                    "SIG (B)",
                    "KeyGen mean (us)",
                    "Sign mean (us)",
                    "Verify mean (us)",
                    "KeyGen p95 (us)",
                    "Sign p95 (us)",
                    "Verify p95 (us)",
                ],
                table_rows,
            ),
        ]
    )
    path.write_text(content + "\n", encoding="utf-8")


def write_aead_md(path: Path, rows: List[Dict[str, Any]]) -> None:
    table_rows: List[List[str]] = []
    for row in rows:
        if "error" in row:
            table_rows.append(
                [
                    row["algorithm"],
                    "n/a",
                    "n/a",
                    "n/a",
                    "n/a",
                    str(row["error"]),
                ]
            )
            continue
        ec = row["encrypt"]
        dc = row["decrypt"]
        table_rows.append(
            [
                row["algorithm"],
                str(row["payload_bytes"]),
                f"{_to_us(ec.mean_ns):.2f}",
                f"{_to_us(dc.mean_ns):.2f}",
                f"{_to_us(ec.p95_ns):.2f}",
                f"{_to_us(dc.p95_ns):.2f}",
            ]
        )

    content = "\n".join(
        [
            "# AEAD Benchmark",
            "",
            "Correctness: decrypted payload matched original plaintext for all timed iterations.",
            "Time source: time.perf_counter_ns().",
            "",
            _md_table(
                [
                    "Algorithm",
                    "Payload (B)",
                    "Encrypt mean (us)",
                    "Decrypt mean (us)",
                    "Encrypt p95 (us)",
                    "Decrypt p95 (us)",
                ],
                table_rows,
            ),
        ]
    )
    path.write_text(content + "\n", encoding="utf-8")


def write_e2e_md(path: Path, result: Dict[str, Any], packet_count: int) -> None:
    ok = bool(result.get("success", False))
    sent = result.get("sent")
    received = result.get("received")
    integrity_ok = isinstance(sent, int) and isinstance(received, int) and received == sent
    rows = [[k, str(v)] for k, v in sorted(result.items(), key=lambda kv: kv[0])]

    content = "\n".join(
        [
            "# Localhost End-to-End Benchmark",
            "",
            f"Suite: {DEFAULT_SUITE_ID}",
            f"Packets requested: {packet_count}",
            f"Run success: {ok}",
            f"Integrity check (received == sent): {integrity_ok}",
            "Time source in tunnel metrics: internal counters + RTT timings from time.perf_counter_ns().",
            "",
            _md_table(["Metric", "Value"], rows),
        ]
    )
    path.write_text(content + "\n", encoding="utf-8")


def write_summary_md(
    path: Path,
    env: Dict[str, str],
    kem_rows: List[Dict[str, Any]],
    sig_rows: List[Dict[str, Any]],
    aead_rows: List[Dict[str, Any]],
    e2e: Dict[str, Any],
    packet_count: int,
) -> None:
    lines: List[str] = [
        "# GCS Benchmark Summary",
        "",
        "## Scope",
        "- Frozen core benchmark campaign executed without modifying protocol semantics.",
        "- Timings collected with time.perf_counter_ns() in benchmark harness.",
        "- Correctness gates applied before accepting timing samples.",
        "",
        "## Environment",
        f"- Host: {env['hostname']}",
        f"- OS: {env['os']}",
        f"- Python: {env['python']}",
        f"- OpenSSL: {env['openssl']}",
        f"- OQS Python: {env['oqs_python']}",
        f"- liboqs: {env['liboqs']}",
        "",
        "## Coverage",
        f"- KEM algorithms: {', '.join(row['algorithm'] for row in kem_rows)}",
        f"- Signature algorithms: {', '.join(row['algorithm'] for row in sig_rows)}",
        f"- AEAD algorithms: {', '.join(sorted({row['algorithm'] for row in aead_rows}))}",
        f"- AEAD payload sizes: {', '.join(str(x) for x in AEAD_PAYLOADS)} bytes",
        f"- E2E localhost packets: {packet_count}",
        "",
        "## E2E Validation",
        f"- Success flag: {bool(e2e.get('success', False))}",
        f"- Received/Sent: {e2e.get('received', 'n/a')}/{e2e.get('sent', 'n/a')}",
        f"- Timeouts: {e2e.get('timeouts', 'n/a')}",
        f"- Mean RTT (us): {e2e.get('rtt_mean_us', 'n/a')}",
        "",
        "## Report Files",
        "- environment.md",
        "- kem-bench.md",
        "- signature-bench.md",
        "- aead-bench.md",
        "- e2e-localhost.md",
        "- benchmark-summary.md",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GCS benchmark campaign and emit markdown reports")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERS)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--packet-count", type=int, default=5000)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = collect_environment()
    kem_rows = benchmark_kem(args.iterations, args.warmup)
    sig_rows = benchmark_signature(args.iterations, args.warmup)
    aead_rows = benchmark_aead(args.iterations, args.warmup)
    e2e = benchmark_e2e(output_dir, args.packet_count)

    write_environment_md(output_dir / "environment.md", env)
    write_kem_md(output_dir / "kem-bench.md", kem_rows)
    write_signature_md(output_dir / "signature-bench.md", sig_rows)
    write_aead_md(output_dir / "aead-bench.md", aead_rows)
    write_e2e_md(output_dir / "e2e-localhost.md", e2e, args.packet_count)
    write_summary_md(
        output_dir / "benchmark-summary.md",
        env,
        kem_rows,
        sig_rows,
        aead_rows,
        e2e,
        args.packet_count,
    )

    artifact = {
        "environment": env,
        "kem": [
            {
                **{k: v for k, v in row.items() if k not in {"keygen", "encap", "decap"}},
                "keygen": row["keygen"].__dict__,
                "encap": row["encap"].__dict__,
                "decap": row["decap"].__dict__,
            }
            for row in kem_rows
        ],
        "signature": [
            {
                **{k: v for k, v in row.items() if k not in {"keygen", "sign", "verify"}},
                "keygen": row["keygen"].__dict__,
                "sign": row["sign"].__dict__,
                "verify": row["verify"].__dict__,
            }
            for row in sig_rows
        ],
        "aead": [
            (
                {
                    **{k: v for k, v in row.items() if k not in {"encrypt", "decrypt"}},
                    "encrypt": row["encrypt"].__dict__,
                    "decrypt": row["decrypt"].__dict__,
                }
                if "encrypt" in row and "decrypt" in row
                else dict(row)
            )
            for row in aead_rows
        ],
        "e2e": e2e,
        "generated_at": _utc_now(),
    }
    (output_dir / "raw-results.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    print(f"Benchmark campaign complete. Reports written to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
