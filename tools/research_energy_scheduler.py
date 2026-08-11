#!/usr/bin/env python3
"""
Research-grade energy/security scheduler for the PQ MAVLink tunnel.

This is intentionally independent from the existing sscheduler package.  It is
designed as a fresh userspace controller for a Raspberry Pi companion computer:

* observes Linux/Pi state, proxy status JSON, and optional link metrics;
* chooses a crypto profile and detector intensity with hysteresis;
* optionally sends a newline-delimited JSON rekey command to core.control_tcp;
* optionally applies Linux scheduling hints to supplied PIDs.

Default mode is dry-run, so it can be studied on a laptop without touching a
running UAV.  Use --apply to actuate control decisions on the Pi.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import enum
import json
import math
import os
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Deque, Iterable, Optional


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.suites import (
        approved_aead_profiles_by_nist_level,
        get_suite,
        list_runtime_suites,
        normalize_aead_token_for_level,
    )
except Exception:  # pragma: no cover - script remains usable outside repo
    approved_aead_profiles_by_nist_level = None
    get_suite = None
    list_runtime_suites = None
    normalize_aead_token_for_level = None


class Mode(str, enum.Enum):
    EMERGENCY = "emergency"
    DEFENSE = "defense"
    ECO = "eco"
    NOMINAL = "nominal"
    SECURE = "secure"


class Action(str, enum.Enum):
    HOLD = "hold"
    REKEY = "rekey"
    DETECTOR = "detector"
    OS_HINTS = "os_hints"


@dataclasses.dataclass(frozen=True)
class CryptoProfile:
    mode: Mode
    suite: str
    aead: str
    detector: str
    governor: str
    note: str


@dataclasses.dataclass(frozen=True)
class Snapshot:
    ts: float
    current_suite: str
    current_aead: str
    pending_suite: str
    pending_aead: str
    rekey_active: bool
    rekey_failures: int
    uptime_s: float
    enc_out: int
    enc_in: int
    drops: int
    encrypt_avg_ns: float
    decrypt_avg_ns: float
    cpu_pct: float
    load1: float
    temp_c: float
    throttled: bool
    mem_available_mb: float
    root_free_mb: float
    packet_rate_hz: float
    drop_rate_hz: float
    watts: Optional[float]
    link_gap_ms: Optional[float]
    rx_pps: Optional[float]


@dataclasses.dataclass(frozen=True)
class Decision:
    action: Action
    target: CryptoProfile
    reasons: tuple[str, ...]
    confidence: float


@dataclasses.dataclass
class SchedulerConfig:
    status_file: Path
    decision_log: Path
    control_host: str
    control_port: int
    interval_s: float
    cooldown_s: float
    stable_upgrade_s: float
    rekey_min_s: float
    cpu_warn_pct: float
    cpu_crit_pct: float
    temp_warn_c: float
    temp_crit_c: float
    min_root_free_mb: float
    packet_attack_hz: float
    drop_attack_hz: float
    link_gap_warn_ms: float
    rx_pps_min: float
    enable_os_hints: bool
    critical_pids: tuple[int, ...]
    tunnel_pids: tuple[int, ...]
    detector_cmd_xgb: Optional[list[str]]
    detector_cmd_tst: Optional[list[str]]


class RollingRate:
    def __init__(self, maxlen: int = 32) -> None:
        self.samples: Deque[tuple[float, int]] = collections.deque(maxlen=maxlen)

    def update(self, ts: float, value: int) -> float:
        self.samples.append((ts, value))
        if len(self.samples) < 2:
            return 0.0
        old_ts, old_val = self.samples[0]
        dt = ts - old_ts
        if dt <= 0:
            return 0.0
        return max(0.0, (value - old_val) / dt)


class SystemSampler:
    def __init__(self) -> None:
        self._last_cpu: Optional[tuple[int, int]] = None

    def sample_cpu_pct(self) -> float:
        try:
            parts = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()
            values = [int(x) for x in parts[1:]]
        except Exception:
            return 0.0
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        cur = (idle, total)
        if self._last_cpu is None:
            self._last_cpu = cur
            return 0.0
        prev_idle, prev_total = self._last_cpu
        self._last_cpu = cur
        total_delta = total - prev_total
        idle_delta = idle - prev_idle
        if total_delta <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta)))

    @staticmethod
    def load1() -> float:
        try:
            return float(os.getloadavg()[0])
        except Exception:
            return 0.0

    @staticmethod
    def temp_c() -> float:
        candidates = [
            Path("/sys/class/thermal/thermal_zone0/temp"),
            Path("/sys/devices/virtual/thermal/thermal_zone0/temp"),
        ]
        for path in candidates:
            try:
                raw = path.read_text(encoding="utf-8").strip()
                return float(raw) / 1000.0
            except Exception:
                continue
        return 0.0

    @staticmethod
    def throttled() -> bool:
        vcgencmd = shutil_which("vcgencmd")
        if vcgencmd is None:
            return False
        try:
            out = subprocess.run(
                [vcgencmd, "get_throttled"],
                check=False,
                capture_output=True,
                text=True,
                timeout=1.0,
            ).stdout.strip()
        except Exception:
            return False
        if "=" not in out:
            return False
        try:
            return int(out.split("=", 1)[1], 16) != 0
        except ValueError:
            return False

    @staticmethod
    def mem_available_mb() -> float:
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemAvailable:"):
                    return float(line.split()[1]) / 1024.0
        except Exception:
            return 0.0
        return 0.0

    @staticmethod
    def root_free_mb() -> float:
        try:
            st = os.statvfs("/")
            return st.f_bavail * st.f_frsize / (1024.0 * 1024.0)
        except Exception:
            return 0.0


def shutil_which(name: str) -> Optional[str]:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}
    except OSError:
        return {}


def nested(data: dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
    for name in names:
        cur: Any = data
        found = True
        for part in name.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                found = False
                break
        if found:
            return cur
    return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def normalize_runtime_aead(suite_id: str, aead: str) -> str:
    if normalize_aead_token_for_level is None or get_suite is None:
        return aead
    try:
        level = str(get_suite(suite_id).get("nist_level", ""))
        return str(normalize_aead_token_for_level(aead, level))
    except Exception:
        return aead


def default_profiles() -> dict[Mode, CryptoProfile]:
    """Build conservative profiles from the tunnel registry when available."""
    suites = list_runtime_suites() if list_runtime_suites is not None else {}
    by_level: dict[str, str] = {}
    for sid, cfg in suites.items():
        if isinstance(cfg, dict):
            by_level[str(cfg.get("nist_level", ""))] = sid

    l1 = by_level.get("L1", "cs-mlkem512-mldsa44")
    l3 = by_level.get("L3", "cs-mlkem768-mldsa65")
    l5 = by_level.get("L5", "cs-mlkem1024-mldsa87")

    aeads: dict[str, tuple[str, ...]] = {}
    if approved_aead_profiles_by_nist_level is not None:
        try:
            aeads = approved_aead_profiles_by_nist_level(runtime_only=True)
        except TypeError:
            aeads = approved_aead_profiles_by_nist_level()
        except Exception:
            aeads = {}

    def pick(level: str, preferred: tuple[str, ...]) -> str:
        allowed = tuple(aeads.get(level, ()))
        if not allowed:
            allowed = preferred
        for token in preferred:
            if token in allowed:
                return token
        return allowed[0]

    l1_aead = pick("L1", ("aesgcm128", "ascon128", "aesccm128"))
    l3_aead = pick("L3", ("aesgcm192", "aesccm192"))
    l5_aead = pick("L5", ("chacha20poly1305", "aesgcm256", "aesccm256"))

    return {
        Mode.EMERGENCY: CryptoProfile(
            Mode.EMERGENCY,
            l1,
            l1_aead,
            "none",
            "powersave",
            "minimum cryptographic and detector cost under unsafe platform state",
        ),
        Mode.ECO: CryptoProfile(
            Mode.ECO,
            l1,
            l1_aead,
            "xgboost",
            "powersave",
            "low-energy mode with lightweight detection",
        ),
        Mode.NOMINAL: CryptoProfile(
            Mode.NOMINAL,
            l3,
            l3_aead,
            "xgboost",
            "schedutil",
            "balanced default for routine UAV operation",
        ),
        Mode.DEFENSE: CryptoProfile(
            Mode.DEFENSE,
            l3,
            l3_aead,
            "tst",
            "performance",
            "attack-response mode; spend CPU on detection before stronger crypto",
        ),
        Mode.SECURE: CryptoProfile(
            Mode.SECURE,
            l5,
            l5_aead,
            "xgboost",
            "schedutil",
            "stable high-security mode when thermal and CPU headroom exist",
        ),
    }


class FreshScheduler:
    def __init__(self, config: SchedulerConfig) -> None:
        self.config = config
        self.profiles = default_profiles()
        self.system = SystemSampler()
        self.enc_rate = RollingRate()
        self.drop_rate = RollingRate()
        self._last_decision: Optional[Decision] = None
        self._last_rekey_ts = 0.0
        self._last_mode_change_ts = 0.0
        self._stable_since: Optional[float] = None
        self._detector_proc: Optional[subprocess.Popen[Any]] = None
        self._detector_level = "none"

    def snapshot(self) -> Snapshot:
        ts = time.time()
        status = read_json(self.config.status_file)
        counters = nested(status, ("counters", "metrics.counters"), {}) or {}
        current_suite = str(nested(status, ("suite", "current_suite", "control.suite"), "") or "")
        current_aead = str(nested(status, ("aead", "aead_token", "control.aead"), "") or "")
        pending_suite = str(nested(status, ("pending_suite", "control.pending_suite"), "") or "")
        pending_aead = str(nested(status, ("pending_aead", "control.pending_aead"), "") or "")
        enc_out = as_int(nested(counters, ("enc_out", "encrypted_out", "packets_encrypted"), 0))
        enc_in = as_int(nested(counters, ("enc_in", "encrypted_in", "packets_decrypted"), 0))
        drops = as_int(nested(counters, ("drop_total", "drops_total", "proxy_drop_total"), 0))
        packet_rate_hz = self.enc_rate.update(ts, enc_in + enc_out)
        drop_rate_hz = self.drop_rate.update(ts, drops)

        watts = nested(status, ("power.watts", "power_avg_w", "power_energy.power_avg_w"), None)
        watts_f = None if watts is None else as_float(watts)

        return Snapshot(
            ts=ts,
            current_suite=current_suite,
            current_aead=current_aead,
            pending_suite=pending_suite,
            pending_aead=pending_aead,
            rekey_active=bool(nested(status, ("rekey_active", "control.rekey_active"), False)),
            rekey_failures=as_int(nested(status, ("rekeys_fail", "control.stats.rekeys_fail"), 0)),
            uptime_s=as_float(nested(status, ("uptime_s", "proxy_uptime_s"), 0.0)),
            enc_out=enc_out,
            enc_in=enc_in,
            drops=drops,
            encrypt_avg_ns=as_float(nested(counters, ("encrypt_avg_ns", "aead_encrypt_avg_ns"), 0.0)),
            decrypt_avg_ns=as_float(nested(counters, ("decrypt_avg_ns", "aead_decrypt_avg_ns"), 0.0)),
            cpu_pct=self.system.sample_cpu_pct(),
            load1=self.system.load1(),
            temp_c=self.system.temp_c(),
            throttled=self.system.throttled(),
            mem_available_mb=self.system.mem_available_mb(),
            root_free_mb=self.system.root_free_mb(),
            packet_rate_hz=packet_rate_hz,
            drop_rate_hz=drop_rate_hz,
            watts=watts_f,
            link_gap_ms=optional_float(nested(status, ("link.gap_p95_ms", "gcs.gap_p95_ms"), None)),
            rx_pps=optional_float(nested(status, ("link.rx_pps", "gcs.rx_pps_median"), None)),
        )

    def decide(self, snap: Snapshot) -> Decision:
        cfg = self.config
        reasons: list[str] = []
        unsafe = False

        if snap.root_free_mb and snap.root_free_mb < cfg.min_root_free_mb:
            unsafe = True
            reasons.append(f"root_free_low={snap.root_free_mb:.0f}MB")
        if snap.temp_c >= cfg.temp_crit_c:
            unsafe = True
            reasons.append(f"temp_critical={snap.temp_c:.1f}C")
        if snap.cpu_pct >= cfg.cpu_crit_pct:
            unsafe = True
            reasons.append(f"cpu_critical={snap.cpu_pct:.1f}%")
        if snap.throttled:
            unsafe = True
            reasons.append("pi_throttled")
        if snap.rekey_failures >= 3:
            unsafe = True
            reasons.append(f"rekey_failures={snap.rekey_failures}")

        link_bad = False
        if snap.link_gap_ms is not None and snap.link_gap_ms > cfg.link_gap_warn_ms:
            link_bad = True
            reasons.append(f"link_gap={snap.link_gap_ms:.0f}ms")
        if snap.rx_pps is not None and snap.rx_pps < cfg.rx_pps_min:
            link_bad = True
            reasons.append(f"rx_pps_low={snap.rx_pps:.1f}")

        attack = (
            snap.packet_rate_hz >= cfg.packet_attack_hz
            or snap.drop_rate_hz >= cfg.drop_attack_hz
        )
        if attack:
            reasons.append(
                f"attack_signal=packet_rate:{snap.packet_rate_hz:.1f},drop_rate:{snap.drop_rate_hz:.1f}"
            )

        stressed = (
            snap.temp_c >= cfg.temp_warn_c
            or snap.cpu_pct >= cfg.cpu_warn_pct
            or link_bad
        )
        if stressed and not unsafe:
            if snap.temp_c >= cfg.temp_warn_c:
                reasons.append(f"temp_warn={snap.temp_c:.1f}C")
            if snap.cpu_pct >= cfg.cpu_warn_pct:
                reasons.append(f"cpu_warn={snap.cpu_pct:.1f}%")

        if unsafe:
            target = self.profiles[Mode.EMERGENCY]
        elif attack and not (snap.temp_c >= cfg.temp_warn_c or snap.cpu_pct >= cfg.cpu_crit_pct):
            target = self.profiles[Mode.DEFENSE]
        elif stressed:
            target = self.profiles[Mode.ECO]
        else:
            if self._stable_since is None:
                self._stable_since = snap.ts
            stable_for = snap.ts - self._stable_since
            target = self.profiles[Mode.SECURE] if stable_for >= cfg.stable_upgrade_s else self.profiles[Mode.NOMINAL]
            reasons.append(f"stable_for={stable_for:.0f}s")

        if unsafe or stressed or attack:
            self._stable_since = None

        if snap.pending_suite or snap.rekey_active:
            return Decision(Action.HOLD, target, tuple(reasons + ["control_plane_busy"]), 0.95)

        current_aead = snap.current_aead or target.aead
        if snap.current_suite == target.suite and normalize_runtime_aead(target.suite, current_aead) == target.aead:
            if target.detector != self._detector_level:
                return Decision(Action.DETECTOR, target, tuple(reasons + ["detector_change"]), 0.8)
            return Decision(Action.OS_HINTS, target, tuple(reasons + ["profile_already_active"]), 0.7)

        if snap.ts - self._last_rekey_ts < cfg.cooldown_s:
            return Decision(Action.HOLD, target, tuple(reasons + ["cooldown"]), 0.8)

        if target.mode not in (Mode.EMERGENCY, Mode.DEFENSE) and snap.uptime_s < cfg.rekey_min_s:
            return Decision(Action.HOLD, target, tuple(reasons + ["min_rekey_age"]), 0.6)

        return Decision(Action.REKEY, target, tuple(reasons), 0.85)

    def apply(self, decision: Decision, *, dry_run: bool) -> dict[str, Any]:
        result: dict[str, Any] = {
            "dry_run": dry_run,
            "action": decision.action.value,
            "target": dataclasses.asdict(decision.target),
            "rekey_response": None,
            "detector": None,
            "os_hints": None,
        }
        if decision.action == Action.REKEY:
            if dry_run:
                result["rekey_response"] = {"ok": True, "dry_run": True}
            else:
                result["rekey_response"] = self._send_rekey(decision.target)
                if result["rekey_response"] and result["rekey_response"].get("ok"):
                    self._last_rekey_ts = time.time()
        if decision.action in (Action.REKEY, Action.DETECTOR):
            result["detector"] = self._set_detector(decision.target.detector, dry_run=dry_run)
        if self.config.enable_os_hints or decision.action == Action.OS_HINTS:
            result["os_hints"] = self._apply_os_hints(decision.target, dry_run=dry_run)
        return result

    def _send_rekey(self, target: CryptoProfile) -> dict[str, Any]:
        payload = {"cmd": "rekey", "suite": target.suite, "aead": target.aead}
        try:
            with socket.create_connection(
                (self.config.control_host, self.config.control_port),
                timeout=3.0,
            ) as sock:
                sock.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
                sock.settimeout(5.0)
                data = b""
                while not data.endswith(b"\n"):
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            if not data:
                return {"ok": False, "error": "empty_control_response"}
            return json.loads(data.decode("utf-8", errors="replace"))
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _set_detector(self, level: str, *, dry_run: bool) -> dict[str, Any]:
        level = level.lower()
        if level == self._detector_level:
            return {"ok": True, "level": level, "changed": False}
        if dry_run:
            return {"ok": True, "level": level, "changed": True, "dry_run": True}

        if self._detector_proc is not None and self._detector_proc.poll() is None:
            self._detector_proc.terminate()
            try:
                self._detector_proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self._detector_proc.kill()
        self._detector_proc = None

        if level == "none":
            self._detector_level = level
            return {"ok": True, "level": level, "changed": True}

        cmd = self.config.detector_cmd_tst if level == "tst" else self.config.detector_cmd_xgb
        if not cmd:
            return {"ok": False, "level": level, "error": "detector_command_not_configured"}
        try:
            self._detector_proc = subprocess.Popen(cmd, cwd=str(ROOT))
            self._detector_level = level
            return {"ok": True, "level": level, "pid": self._detector_proc.pid}
        except Exception as exc:
            return {"ok": False, "level": level, "error": f"{type(exc).__name__}: {exc}"}

    def _apply_os_hints(self, target: CryptoProfile, *, dry_run: bool) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "governor": target.governor,
                "critical_pids": self.config.critical_pids,
                "tunnel_pids": self.config.tunnel_pids,
            }

        gov_result = set_governor(target.governor)
        actions.append({"governor": gov_result})

        for pid in self.config.critical_pids:
            actions.append({"pid": pid, "affinity": set_affinity(pid, {0}), "nice": renice(pid, -5)})
        tunnel_cores = {1, 2, 3} if os.cpu_count() and os.cpu_count() >= 4 else set(range(os.cpu_count() or 1))
        for pid in self.config.tunnel_pids:
            actions.append({"pid": pid, "affinity": set_affinity(pid, tunnel_cores), "nice": renice(pid, 0)})
        return {"ok": all(x.get("ok", True) for x in flatten_actions(actions)), "actions": actions}


def optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def set_governor(governor: str) -> dict[str, Any]:
    paths = sorted(Path("/sys/devices/system/cpu/cpufreq").glob("policy*/scaling_governor"))
    if not paths:
        return {"ok": False, "error": "no_cpufreq_policy"}
    errors: list[str] = []
    for path in paths:
        try:
            path.write_text(governor, encoding="utf-8")
        except Exception as exc:
            errors.append(f"{path}:{exc}")
    return {"ok": not errors, "errors": errors}


def set_affinity(pid: int, cpus: set[int]) -> dict[str, Any]:
    try:
        os.sched_setaffinity(pid, cpus)
        return {"ok": True, "cpus": sorted(cpus)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def renice(pid: int, nice: int) -> dict[str, Any]:
    try:
        os.setpriority(os.PRIO_PROCESS, pid, nice)
        return {"ok": True, "nice": nice}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def flatten_actions(actions: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in actions:
        if isinstance(item, dict):
            out.append(item)
            for value in item.values():
                if isinstance(value, dict):
                    out.append(value)
    return out


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def parse_cmd(value: Optional[str]) -> Optional[list[str]]:
    if not value:
        return None
    import shlex

    return shlex.split(value)


def parse_pids(values: list[str]) -> tuple[int, ...]:
    out: list[int] = []
    for raw in values:
        for part in raw.split(","):
            part = part.strip()
            if part:
                out.append(int(part))
    return tuple(out)


def build_config(args: argparse.Namespace) -> SchedulerConfig:
    return SchedulerConfig(
        status_file=Path(args.status_file),
        decision_log=Path(args.decision_log),
        control_host=args.control_host,
        control_port=args.control_port,
        interval_s=args.interval,
        cooldown_s=args.cooldown,
        stable_upgrade_s=args.stable_upgrade,
        rekey_min_s=args.rekey_min_age,
        cpu_warn_pct=args.cpu_warn,
        cpu_crit_pct=args.cpu_crit,
        temp_warn_c=args.temp_warn,
        temp_crit_c=args.temp_crit,
        min_root_free_mb=args.min_root_free_mb,
        packet_attack_hz=args.packet_attack_hz,
        drop_attack_hz=args.drop_attack_hz,
        link_gap_warn_ms=args.link_gap_warn_ms,
        rx_pps_min=args.rx_pps_min,
        enable_os_hints=args.os_hints,
        critical_pids=parse_pids(args.critical_pid),
        tunnel_pids=parse_pids(args.tunnel_pid),
        detector_cmd_xgb=parse_cmd(args.detector_cmd_xgb),
        detector_cmd_tst=parse_cmd(args.detector_cmd_tst),
    )


def run_once(scheduler: FreshScheduler, *, dry_run: bool) -> dict[str, Any]:
    snap = scheduler.snapshot()
    decision = scheduler.decide(snap)
    apply_result = scheduler.apply(decision, dry_run=dry_run)
    record = {
        "ts": snap.ts,
        "snapshot": dataclasses.asdict(snap),
        "decision": {
            "action": decision.action.value,
            "target": dataclasses.asdict(decision.target),
            "reasons": list(decision.reasons),
            "confidence": decision.confidence,
        },
        "apply": apply_result,
    }
    append_jsonl(scheduler.config.decision_log, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fresh research scheduler for Pi-hosted PQ MAVLink tunnel"
    )
    parser.add_argument("--status-file", default=str(ROOT / "logs" / "drone_status.json"))
    parser.add_argument("--decision-log", default=str(ROOT / "logs" / "research_scheduler.jsonl"))
    parser.add_argument("--control-host", default="127.0.0.1")
    parser.add_argument("--control-port", type=int, default=48080)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--cooldown", type=float, default=20.0)
    parser.add_argument("--stable-upgrade", type=float, default=180.0)
    parser.add_argument("--rekey-min-age", type=float, default=30.0)
    parser.add_argument("--cpu-warn", type=float, default=72.0)
    parser.add_argument("--cpu-crit", type=float, default=90.0)
    parser.add_argument("--temp-warn", type=float, default=70.0)
    parser.add_argument("--temp-crit", type=float, default=80.0)
    parser.add_argument("--min-root-free-mb", type=float, default=1024.0)
    parser.add_argument("--packet-attack-hz", type=float, default=250.0)
    parser.add_argument("--drop-attack-hz", type=float, default=20.0)
    parser.add_argument("--link-gap-warn-ms", type=float, default=1000.0)
    parser.add_argument("--rx-pps-min", type=float, default=5.0)
    parser.add_argument("--critical-pid", action="append", default=[])
    parser.add_argument("--tunnel-pid", action="append", default=[])
    parser.add_argument("--detector-cmd-xgb")
    parser.add_argument("--detector-cmd-tst")
    parser.add_argument("--os-hints", action="store_true")
    parser.add_argument("--apply", action="store_true", help="actuate rekey/detector/OS hints")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--print", action="store_true", help="print each decision JSON")
    args = parser.parse_args()

    cfg = build_config(args)
    scheduler = FreshScheduler(cfg)
    dry_run = not args.apply

    while True:
        record = run_once(scheduler, dry_run=dry_run)
        if args.print:
            print(json.dumps(record, indent=2, sort_keys=True))
        if args.once:
            return 0
        time.sleep(max(0.2, cfg.interval_s))


if __name__ == "__main__":
    raise SystemExit(main())
