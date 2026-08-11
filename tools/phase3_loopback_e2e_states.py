#!/usr/bin/env python3
"""Phase 3 loopback E2E state-transition tests with live AEAD traffic.

Runs core-only localhost tests:
- start GCS/Drone proxies
- keep plaintext UDP request/echo stream active
- trigger rekey via TCP control command
- observe policy states (RUNNING/NEGOTIATING/SWAPPING)
- measure traffic pre/during/post rekey
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.async_proxy import run_proxy  # noqa: E402
from core.config import CONFIG  # noqa: E402
from core.suites import aead_profiles_by_nist_level, list_suites  # noqa: E402


@dataclass(frozen=True)
class Case:
    case_id: str
    category: str
    source_suite: str
    source_aead: str
    target_suite: str
    target_aead: str
    source_level: str
    target_level: str


def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_signature_class():
    try:
        from oqs.oqs import Signature  # type: ignore
    except Exception:  # pragma: no cover - env dependent
        from oqs import Signature  # type: ignore
    return Signature


class IdentityStore:
    """Lazily builds per-suite signing identity for rekey transitions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._secret: Dict[str, object] = {}
        self._public: Dict[str, bytes] = {}
        self._Signature = _load_signature_class()
        self._suite_map = list_suites()

    def ensure(self, suite_id: str) -> Tuple[object, bytes]:
        with self._lock:
            secret = self._secret.get(suite_id)
            public = self._public.get(suite_id)
            if secret is not None and public is not None:
                return secret, public

            suite = self._suite_map[suite_id]
            sig_name = str(suite["sig_name"])
            signer = self._Signature(sig_name)
            pub = signer.generate_keypair()
            self._secret[suite_id] = signer
            self._public[suite_id] = pub
            return signer, pub

    def secret_loader(self, target_suite: Dict[str, object]) -> object:
        sid = str(target_suite.get("suite_id", ""))
        if not sid:
            raise RuntimeError("target_suite missing suite_id")
        secret, _ = self.ensure(sid)
        return secret

    def public_loader(self, target_suite: Dict[str, object]) -> bytes:
        sid = str(target_suite.get("suite_id", ""))
        if not sid:
            raise RuntimeError("target_suite missing suite_id")
        _, public = self.ensure(sid)
        return public

    def close(self) -> None:
        with self._lock:
            for signer in self._secret.values():
                try:
                    if hasattr(signer, "free"):
                        signer.free()
                except Exception:
                    pass
            self._secret.clear()
            self._public.clear()


def _send_tcp_json(host: str, port: int, payload: Dict[str, object], timeout_s: float = 2.0) -> Dict[str, object]:
    line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    with socket.create_connection((host, int(port)), timeout=timeout_s) as sock:
        sock.settimeout(timeout_s)
        sock.sendall(line)
        data = b""
        while b"\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    text = data.decode("utf-8", errors="replace").strip()
    if not text:
        return {"ok": False, "error": "empty_control_response"}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"bad_control_json:{text[:160]}"}


def _build_cfg_for_case(*, base_port: int, source_aead: str, run_dir: Path) -> Dict[str, object]:
    cfg = dict(CONFIG)
    cfg.update(
        {
            "DRONE_HOST": "127.0.0.1",
            "GCS_HOST": "127.0.0.1",
            "DRONE_HOST_LAN": "127.0.0.1",
            "GCS_HOST_LAN": "127.0.0.1",
            "DRONE_HOST_TAILSCALE": "127.0.0.1",
            "GCS_HOST_TAILSCALE": "127.0.0.1",
            "TCP_HANDSHAKE_PORT": base_port + 0,
            "UDP_GCS_RX": base_port + 1,
            "UDP_DRONE_RX": base_port + 2,
            "GCS_PLAINTEXT_TX": base_port + 3,
            "GCS_PLAINTEXT_RX": base_port + 4,
            "DRONE_PLAINTEXT_TX": base_port + 5,
            "DRONE_PLAINTEXT_RX": base_port + 6,
            "GCS_CONTROL_HOST": "127.0.0.1",
            "GCS_CONTROL_PORT": base_port + 7,
            "DRONE_CONTROL_HOST": "127.0.0.1",
            "DRONE_CONTROL_PORT": base_port + 8,
            "ENABLE_TCP_CONTROL": True,
            "CONTROL_COORDINATOR_ROLE": "gcs",
            "STRICT_HANDSHAKE_IP": False,
            "STRICT_UDP_PEER_MATCH": True,
            "ALLOW_NON_LOOPBACK_PLAINTEXT": True,
            "GCS_PLAINTEXT_SNIFF_PORT": 0,
            "SUITE_AEAD_TOKEN": source_aead,
            "DRONE_PSK": "ab" * 32,
            "REKEY_HANDSHAKE_TIMEOUT": 20.0,
            "CONTROL_NEGOTIATING_TIMEOUT_S": 20.0,
            "CONTROL_SWAPPING_TIMEOUT_S": 40.0,
            "ENCRYPTED_DSCP": None,
            "MAVLINK_SNIFF_DRONE": base_port + 9,
            "MAVLINK_SNIFF_GCS": base_port + 10,
            "QGC_PORT": base_port + 11,
        }
    )
    cfg["__RUN_DIR"] = str(run_dir)
    return cfg


def _drone_echo_worker(
    *,
    host: str,
    rx_port: int,
    tx_port: int,
    stop_event: threading.Event,
    stats: Dict[str, int],
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, int(rx_port)))
    sock.settimeout(0.2)
    try:
        while not stop_event.is_set():
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                continue
            stats["recv"] = stats.get("recv", 0) + 1
            try:
                sock.sendto(data, (host, int(tx_port)))
                stats["echo"] = stats.get("echo", 0) + 1
            except OSError:
                stats["send_err"] = stats.get("send_err", 0) + 1
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _traffic_worker(
    *,
    case_id: str,
    host: str,
    tx_port: int,
    rx_port: int,
    stop_event: threading.Event,
    traffic_log: List[Dict[str, object]],
    interval_s: float = 0.02,
    timeout_s: float = 0.15,
) -> None:
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    recv_sock.bind((host, int(rx_port)))
    recv_sock.settimeout(timeout_s)

    seq = 0
    try:
        while not stop_event.is_set():
            sent_ts = time.monotonic()
            payload = f"{case_id}|{seq}|{int(time.time_ns())}".encode("utf-8")
            try:
                send_sock.sendto(payload, (host, int(tx_port)))
                ok = False
                rtt_ms: Optional[float] = None
                try:
                    echoed, _ = recv_sock.recvfrom(65535)
                    if echoed == payload:
                        ok = True
                        rtt_ms = (time.monotonic() - sent_ts) * 1000.0
                except socket.timeout:
                    ok = False
                traffic_log.append(
                    {
                        "ts_mono": sent_ts,
                        "seq": seq,
                        "ok": ok,
                        "rtt_ms": None if rtt_ms is None else round(rtt_ms, 3),
                    }
                )
            except OSError:
                traffic_log.append({"ts_mono": sent_ts, "seq": seq, "ok": False, "rtt_ms": None, "send_error": True})
            seq += 1
            time.sleep(interval_s)
    finally:
        try:
            send_sock.close()
        except Exception:
            pass
        try:
            recv_sock.close()
        except Exception:
            pass


def _status_poll_worker(
    *,
    host: str,
    port: int,
    stop_event: threading.Event,
    status_log: List[Dict[str, object]],
    interval_s: float = 0.02,
) -> None:
    while not stop_event.is_set():
        ts = time.monotonic()
        try:
            resp = _send_tcp_json(host, port, {"cmd": "status"}, timeout_s=0.5)
            status_log.append(
                {
                    "ts_mono": ts,
                    "ok": bool(resp.get("ok")),
                    "state": resp.get("state"),
                    "last_rekey_suite": resp.get("last_rekey_suite"),
                    "last_rekey_ms": resp.get("last_rekey_ms"),
                    "last_status": resp.get("last_status"),
                    "pending_suite": resp.get("pending_suite"),
                    "error": resp.get("error", ""),
                }
            )
        except Exception as exc:
            status_log.append(
                {
                    "ts_mono": ts,
                    "ok": False,
                    "state": "",
                    "last_rekey_suite": "",
                    "last_rekey_ms": 0,
                    "last_status": {},
                    "pending_suite": "",
                    "error": f"poll_error:{type(exc).__name__}:{exc}",
                }
            )
        time.sleep(interval_s)


def _partition_traffic(
    *,
    traffic_log: List[Dict[str, object]],
    t_cmd: float,
    t_done: Optional[float],
) -> Dict[str, Dict[str, object]]:
    def summarize(items: List[Dict[str, object]]) -> Dict[str, object]:
        sent = len(items)
        ok = sum(1 for x in items if bool(x.get("ok")))
        fail = sent - ok
        rtts = [float(x["rtt_ms"]) for x in items if x.get("ok") and x.get("rtt_ms") is not None]
        return {
            "sent": sent,
            "ok": ok,
            "fail": fail,
            "loss_pct": 0.0 if sent == 0 else round((fail * 100.0) / sent, 3),
            "rtt_avg_ms": 0.0 if not rtts else round(sum(rtts) / len(rtts), 3),
            "rtt_max_ms": 0.0 if not rtts else round(max(rtts), 3),
        }

    pre: List[Dict[str, object]] = []
    during: List[Dict[str, object]] = []
    post: List[Dict[str, object]] = []
    for item in traffic_log:
        ts = float(item["ts_mono"])
        if ts < t_cmd:
            pre.append(item)
        elif t_done is None or ts < t_done:
            during.append(item)
        else:
            post.append(item)
    return {
        "pre": summarize(pre),
        "during": summarize(during),
        "post": summarize(post),
        "total": summarize(list(traffic_log)),
    }


def _pick_suite(level_suites: List[str], *, prefer_mlkem: bool = True) -> str:
    if prefer_mlkem:
        for sid in level_suites:
            if "cs-mlkem" in sid:
                return sid
    return level_suites[0]


def _pick_secondary_suite(level_suites: List[str], primary: str) -> str:
    mlkem_candidates = [sid for sid in level_suites if sid.startswith("cs-mlkem") and sid != primary]
    if mlkem_candidates:
        return mlkem_candidates[0]
    for sid in level_suites:
        if sid != primary:
            return sid
    return primary


def _build_cases() -> List[Case]:
    suites = list_suites()  # runtime-pruned
    by_level: Dict[str, List[str]] = {"L1": [], "L3": [], "L5": []}
    for sid, cfg in suites.items():
        lvl = str(cfg.get("nist_level", "")).upper()
        if lvl in by_level:
            by_level[lvl].append(sid)
    for lvl in by_level:
        by_level[lvl].sort()
    for lvl in ("L1", "L3", "L5"):
        if not by_level[lvl]:
            raise RuntimeError(f"No runtime suites available for level {lvl}")

    profiles = aead_profiles_by_nist_level(runtime_only=True)
    for lvl in ("L1", "L3", "L5"):
        if not profiles.get(lvl):
            raise RuntimeError(f"No runtime AEAD profiles for level {lvl}")

    l1_primary = _pick_suite(by_level["L1"])
    l3_primary = _pick_suite(by_level["L3"])
    l5_primary = _pick_suite(by_level["L5"])

    l1_secondary = _pick_secondary_suite(by_level["L1"], l1_primary)

    l1_tokens = list(profiles["L1"])
    l3_tokens = list(profiles["L3"])
    l5_tokens = list(profiles["L5"])

    def prefer(tokens: List[str], preferred: str, fallback: str) -> str:
        if preferred in tokens:
            return preferred
        if fallback in tokens:
            return fallback
        return tokens[0]

    l1_gcm = prefer(l1_tokens, "aesgcm", l1_tokens[0])
    l1_ascon = prefer(l1_tokens, "ascon128a", l1_tokens[-1])
    l1_ccm = prefer(l1_tokens, "aesccm", l1_tokens[0])

    l3_gcm = prefer(l3_tokens, "aesgcm", l3_tokens[0])
    l3_ccm = prefer(l3_tokens, "aesccm", l3_tokens[0])

    l5_gcm = prefer(l5_tokens, "aesgcm", l5_tokens[0])
    l5_chacha = prefer(l5_tokens, "chacha20poly1305", l5_tokens[-1])

    cases: List[Case] = [
        Case(
            case_id="same_suite_same_aead_l3",
            category="same_suite_same_aead",
            source_suite=l3_primary,
            source_aead=l3_gcm,
            target_suite=l3_primary,
            target_aead=l3_gcm,
            source_level="L3",
            target_level="L3",
        ),
        Case(
            case_id="same_suite_aead_only_l3_gcm_to_ccm",
            category="aead_only_same_suite",
            source_suite=l3_primary,
            source_aead=l3_gcm,
            target_suite=l3_primary,
            target_aead=l3_ccm,
            source_level="L3",
            target_level="L3",
        ),
        Case(
            case_id="same_suite_aead_only_l1_gcm_to_ascon",
            category="aead_only_same_suite",
            source_suite=l1_primary,
            source_aead=l1_gcm,
            target_suite=l1_primary,
            target_aead=l1_ascon,
            source_level="L1",
            target_level="L1",
        ),
        Case(
            case_id="same_suite_aead_only_l5_gcm_to_chacha",
            category="aead_only_same_suite",
            source_suite=l5_primary,
            source_aead=l5_gcm,
            target_suite=l5_primary,
            target_aead=l5_chacha,
            source_level="L5",
            target_level="L5",
        ),
        Case(
            case_id="diff_suite_same_level_l1",
            category="full_handshake_same_level",
            source_suite=l1_primary,
            source_aead=l1_gcm,
            target_suite=l1_secondary,
            target_aead=l1_ccm,
            source_level="L1",
            target_level="L1",
        ),
        Case(
            case_id="diff_suite_cross_level_l1_to_l5",
            category="full_handshake_cross_level",
            source_suite=l1_primary,
            source_aead=l1_gcm,
            target_suite=l5_primary,
            target_aead=l5_chacha,
            source_level="L1",
            target_level="L5",
        ),
    ]
    return cases


def _run_case(case: Case, *, index: int, out_dir: Path) -> Dict[str, object]:
    base_port = 55000 + (index * 40)
    case_dir = out_dir / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    cfg = _build_cfg_for_case(base_port=base_port, source_aead=case.source_aead, run_dir=case_dir)

    # Ensure deterministic test PSK.
    os.environ["DRONE_PSK"] = str(cfg["DRONE_PSK"])

    suites = list_suites()
    source_suite = suites[case.source_suite]
    target_suite = suites[case.target_suite]
    source_suite = {**source_suite, "suite_id": case.source_suite, "aead_token": case.source_aead}
    target_suite = {**target_suite, "suite_id": case.target_suite, "aead_token": case.target_aead}

    identities = IdentityStore()
    source_secret, source_public = identities.ensure(case.source_suite)

    proxy_timeout_s = 26.0
    start_delay_s = 0.5
    warmup_s = 2.5
    post_rekey_observe_s = 2.5
    rekey_timeout_s = 20.0

    gcs_status_file = case_dir / "gcs.status.json"
    drone_status_file = case_dir / "drone.status.json"

    proxy_errors: List[str] = []
    proxy_counters: Dict[str, Dict[str, object]] = {}

    def proxy_runner(name: str, **kwargs: object) -> None:
        try:
            counters = run_proxy(**kwargs)  # type: ignore[arg-type]
            proxy_counters[name] = counters
        except Exception as exc:
            proxy_errors.append(f"{name}:{type(exc).__name__}:{exc}")

    echo_stop = threading.Event()
    echo_stats: Dict[str, int] = {}
    echo_thread = threading.Thread(
        target=_drone_echo_worker,
        kwargs={
            "host": "127.0.0.1",
            "rx_port": int(cfg["DRONE_PLAINTEXT_RX"]),
            "tx_port": int(cfg["DRONE_PLAINTEXT_TX"]),
            "stop_event": echo_stop,
            "stats": echo_stats,
        },
        daemon=True,
    )
    echo_thread.start()

    gcs_thread = threading.Thread(
        target=proxy_runner,
        kwargs={
            "name": "gcs",
            "role": "gcs",
            "suite": source_suite,
            "cfg": cfg,
            "gcs_sig_secret": source_secret,
            "gcs_sig_public": None,
            "stop_after_seconds": proxy_timeout_s,
            "manual_control": False,
            "quiet": True,
            "status_file": str(gcs_status_file),
            "load_gcs_secret": identities.secret_loader,
        },
        daemon=True,
    )
    drone_thread = threading.Thread(
        target=proxy_runner,
        kwargs={
            "name": "drone",
            "role": "drone",
            "suite": source_suite,
            "cfg": cfg,
            "gcs_sig_secret": None,
            "gcs_sig_public": source_public,
            "stop_after_seconds": proxy_timeout_s,
            "manual_control": False,
            "quiet": True,
            "status_file": str(drone_status_file),
            "load_gcs_public": identities.public_loader,
        },
        daemon=True,
    )

    case_start = time.monotonic()
    gcs_thread.start()
    time.sleep(start_delay_s)
    drone_thread.start()

    # Wait for control plane readiness.
    ready = False
    ready_err = ""
    for _ in range(60):
        try:
            ping = _send_tcp_json("127.0.0.1", int(cfg["GCS_CONTROL_PORT"]), {"cmd": "ping"}, timeout_s=0.5)
            if ping.get("ok"):
                ready = True
                break
            ready_err = str(ping.get("error", "ping_not_ok"))
        except Exception as exc:
            ready_err = str(exc)
        time.sleep(0.1)

    traffic_log: List[Dict[str, object]] = []
    status_log: List[Dict[str, object]] = []
    traffic_stop = threading.Event()
    status_stop = threading.Event()
    traffic_thread: Optional[threading.Thread] = None
    status_thread: Optional[threading.Thread] = None
    rekey_response: Dict[str, object] = {"ok": False, "error": "not_sent"}
    t_cmd: Optional[float] = None
    t_done: Optional[float] = None
    observed_states: List[str] = []
    rekey_ok = False
    rekey_error = ""

    try:
        if not ready:
            rekey_error = f"control_not_ready:{ready_err}"
        else:
            traffic_thread = threading.Thread(
                target=_traffic_worker,
                kwargs={
                    "case_id": case.case_id,
                    "host": "127.0.0.1",
                    "tx_port": int(cfg["GCS_PLAINTEXT_TX"]),
                    "rx_port": int(cfg["GCS_PLAINTEXT_RX"]),
                    "stop_event": traffic_stop,
                    "traffic_log": traffic_log,
                },
                daemon=True,
            )
            status_thread = threading.Thread(
                target=_status_poll_worker,
                kwargs={
                    "host": "127.0.0.1",
                    "port": int(cfg["GCS_CONTROL_PORT"]),
                    "stop_event": status_stop,
                    "status_log": status_log,
                },
                daemon=True,
            )
            traffic_thread.start()
            status_thread.start()
            time.sleep(warmup_s)

            rekey_payload = {
                "cmd": "rekey",
                "suite": case.target_suite,
                "aead": case.target_aead,
            }
            t_cmd = time.monotonic()
            rekey_response = _send_tcp_json("127.0.0.1", int(cfg["GCS_CONTROL_PORT"]), rekey_payload, timeout_s=2.0)
            rid = str(rekey_response.get("rid", ""))
            if not rekey_response.get("ok") or not rid:
                rekey_error = f"rekey_rejected:{rekey_response}"
            else:
                deadline = time.monotonic() + rekey_timeout_s
                baseline_last_ms = 0
                if status_log:
                    last = status_log[-1]
                    try:
                        baseline_last_ms = int(last.get("last_rekey_ms") or 0)
                    except Exception:
                        baseline_last_ms = 0
                while time.monotonic() < deadline:
                    st = _send_tcp_json("127.0.0.1", int(cfg["GCS_CONTROL_PORT"]), {"cmd": "status"}, timeout_s=1.0)
                    state = str(st.get("state", ""))
                    if state:
                        observed_states.append(state)
                    if state == "RUNNING":
                        try:
                            new_last_ms = int(st.get("last_rekey_ms") or 0)
                        except Exception:
                            new_last_ms = 0
                        if str(st.get("last_rekey_suite", "")) == case.target_suite and new_last_ms >= baseline_last_ms:
                            t_done = time.monotonic()
                            rekey_ok = True
                            break
                    time.sleep(0.2)
                if not rekey_ok:
                    rekey_error = "rekey_timeout_or_status_mismatch"

            time.sleep(post_rekey_observe_s)
    finally:
        traffic_stop.set()
        status_stop.set()
        if traffic_thread is not None:
            traffic_thread.join(timeout=2.0)
        if status_thread is not None:
            status_thread.join(timeout=2.0)
        echo_stop.set()
        echo_thread.join(timeout=2.0)
        # Proxies auto-stop via stop_after_seconds
        gcs_thread.join(timeout=proxy_timeout_s + 5.0)
        drone_thread.join(timeout=proxy_timeout_s + 5.0)
        identities.close()

    # Build result object.
    if t_cmd is None:
        t_cmd = case_start
    traffic_partition = _partition_traffic(traffic_log=traffic_log, t_cmd=t_cmd, t_done=t_done)
    observed = sorted(set(observed_states + [str(x.get("state", "")) for x in status_log if x.get("state")]))
    if observed and observed[-1] == "":
        observed = [x for x in observed if x]

    states_required = {"RUNNING", "NEGOTIATING", "SWAPPING"}
    states_seen = set(observed)
    # Very short negotiations can be hard to sample; require RUNNING + one transient state.
    states_ok = ("RUNNING" in states_seen) and (("NEGOTIATING" in states_seen) or ("SWAPPING" in states_seen))

    result = {
        "case_id": case.case_id,
        "category": case.category,
        "source": {
            "suite": case.source_suite,
            "aead": case.source_aead,
            "level": case.source_level,
        },
        "target": {
            "suite": case.target_suite,
            "aead": case.target_aead,
            "level": case.target_level,
        },
        "control_ready": ready,
        "rekey_response": rekey_response,
        "rekey_ok": rekey_ok,
        "rekey_error": rekey_error,
        "observed_states": observed,
        "states_ok": states_ok,
        "traffic": traffic_partition,
        "traffic_events": len(traffic_log),
        "status_events": len(status_log),
        "echo_stats": echo_stats,
        "proxy_errors": proxy_errors,
        "proxy_counters_summary": {
            role: {
                "rekeys_ok": int((ctr or {}).get("rekeys_ok", 0)),
                "rekeys_fail": int((ctr or {}).get("rekeys_fail", 0)),
                "drops": int((ctr or {}).get("drops", 0)),
                "enc_in": int((ctr or {}).get("enc_in", 0)),
                "enc_out": int((ctr or {}).get("enc_out", 0)),
                "ptx_in": int((ctr or {}).get("ptx_in", 0)),
                "ptx_out": int((ctr or {}).get("ptx_out", 0)),
            }
            for role, ctr in proxy_counters.items()
        },
        "timing": {
            "case_start_mono": case_start,
            "rekey_cmd_mono": t_cmd,
            "rekey_done_mono": t_done,
            "case_elapsed_s": round(time.monotonic() - case_start, 3),
        },
        "pass": bool(
            ready
            and rekey_ok
            and not proxy_errors
            and states_ok
            and traffic_partition["pre"]["ok"] > 0
            and traffic_partition["during"]["ok"] > 0
            and traffic_partition["post"]["ok"] > 0
        ),
    }

    (case_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def run_all(*, out_dir: Path) -> Dict[str, object]:
    started = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = _build_cases()
    results: List[Dict[str, object]] = []
    for idx, case in enumerate(cases):
        print(f"[{idx + 1}/{len(cases)}] {case.case_id} ({case.category})")
        result = _run_case(case, index=idx, out_dir=out_dir)
        results.append(result)
        mark = "PASS" if result["pass"] else "FAIL"
        print(f"  -> {mark} rekey_ok={result['rekey_ok']} states_ok={result['states_ok']} "
              f"traffic_ok={result['traffic']['total']['ok']}/{result['traffic']['total']['sent']}")

    total = len(results)
    passed = sum(1 for r in results if r.get("pass"))
    failed = total - passed
    category_counts: Dict[str, int] = {}
    for r in results:
        cat = str(r.get("category", "unknown"))
        category_counts[cat] = category_counts.get(cat, 0) + 1

    summary = {
        "generated_at_utc": _now_utc(),
        "elapsed_s": round(time.time() - started, 3),
        "total_cases": total,
        "passed": passed,
        "failed": failed,
        "category_counts": category_counts,
        "results": results,
    }
    summary_path = out_dir / "phase3_loopback_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 3 loopback E2E state tests")
    parser.add_argument(
        "--out-dir",
        default=str(Path("logs") / "phase3_loopback"),
        help="Output directory for per-case logs and summary",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero exit code when any case fails",
    )
    args = parser.parse_args()
    out_dir = Path(args.out_dir).expanduser().resolve()
    summary = run_all(out_dir=out_dir)
    print("Phase 3 loopback E2E summary")
    print(f"- cases: {summary['total_cases']}")
    print(f"- passed: {summary['passed']}")
    print(f"- failed: {summary['failed']}")
    print(f"- report: {summary['summary_path']}")
    if args.strict and int(summary["failed"]) != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
