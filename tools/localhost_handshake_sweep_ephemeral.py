import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs" / "localhost_handshake_sweep_ephemeral"
LOG_DIR.mkdir(parents=True, exist_ok=True)

PUB_RE = re.compile(r"Public key \(hex\):\s*([0-9a-fA-F]+)")

PRIMARY_CLASSES = {
    "pass",
    "startup-keyload-fail",
    "identity-mismatch-fail",
    "handshake-verify-fail",
    "transport-connect-fail",
    "control-plane-transition-fail",
    "interrupted",
}


def _tail_text(path: Path, max_chars: int = 4000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _contains_any(haystack: str, needles: List[str]) -> bool:
    lowered = (haystack or "").lower()
    return any(n.lower() in lowered for n in needles)


def _classify_failure(
    *,
    passed: bool,
    interrupted: bool,
    drone_rc: int,
    drone_stdout: str,
    drone_stderr: str,
    gcs_stdout: str,
    gcs_stderr: str,
    status_ok: bool,
    pubkey_ready: bool,
) -> Dict[str, str]:
    if interrupted:
        return {
            "primary_class": "interrupted",
            "secondary_class": "signal-interrupt",
            "failure_phase": "interrupted",
        }
    if passed:
        return {
            "primary_class": "pass",
            "secondary_class": "",
            "failure_phase": "none",
        }

    combined = "\n".join([drone_stdout or "", drone_stderr or "", gcs_stdout or "", gcs_stderr or ""])

    if not pubkey_ready:
        return {
            "primary_class": "startup-keyload-fail",
            "secondary_class": "ephemeral-pubkey-export-missing",
            "failure_phase": "startup",
        }

    if _contains_any(
        combined,
        [
            "invalid signing identity",
            "signing identity self-test failed",
            "public key does not match",
            "identity mismatch",
        ],
    ):
        return {
            "primary_class": "identity-mismatch-fail",
            "secondary_class": "signer-public-consistency",
            "failure_phase": "startup",
        }

    if _contains_any(
        combined,
        [
            "bad signature",
            "failed authentication",
            "handshakeverifyerror",
            "key confirmation",
            "psk",
        ],
    ):
        return {
            "primary_class": "handshake-verify-fail",
            "secondary_class": "auth-or-transcript",
            "failure_phase": "protocol",
        }

    if _contains_any(
        combined,
        [
            "handshake tcp connect failed",
            "actively refused",
            "timed out",
            "no drone tcp handshake connection received",
            "connection reset",
            "connection closed",
        ],
    ):
        return {
            "primary_class": "transport-connect-fail",
            "secondary_class": "tcp-handshake-connect",
            "failure_phase": "startup" if drone_rc != 0 and not status_ok else "protocol",
        }

    if not status_ok:
        return {
            "primary_class": "control-plane-transition-fail",
            "secondary_class": "status-artifact-mismatch",
            "failure_phase": "protocol",
        }

    return {
        "primary_class": "handshake-verify-fail",
        "secondary_class": "unclassified-handshake",
        "failure_phase": "protocol",
    }


def list_runtime_suites() -> list[str]:
    code = "import core.suites as s; print('\\n'.join(sorted(s.SUITES.keys())))"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


class GcsReader:
    def __init__(self, proc: subprocess.Popen, out_path: Path):
        self.proc = proc
        self.out_path = out_path
        self.lines = []
        self.pub_hex = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        with open(self.out_path, "w", encoding="utf-8") as f:
            while True:
                line = self.proc.stdout.readline() if self.proc.stdout is not None else ""
                if not line:
                    break
                f.write(line)
                f.flush()
                with self._lock:
                    self.lines.append(line)
                m = PUB_RE.search(line)
                if m and not self.pub_hex:
                    self.pub_hex = m.group(1)
                    self._ready.set()
        self._done.set()

    def wait_pub(self, timeout_s: float) -> str | None:
        ok = self._ready.wait(timeout=timeout_s)
        if not ok:
            return None
        return self.pub_hex

    def text(self) -> str:
        with self._lock:
            return "".join(self.lines)



def run_one_suite(suite_id: str, stop_seconds: int = 14) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    env["DRONE_HOST"] = "127.0.0.1"
    env["GCS_HOST"] = "127.0.0.1"
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")

    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", suite_id)
    gcs_status = LOG_DIR / f"{safe}.gcs.status.json"
    drone_status = LOG_DIR / f"{safe}.drone.status.json"
    gcs_json = LOG_DIR / f"{safe}.gcs.counters.json"
    drone_json = LOG_DIR / f"{safe}.drone.counters.json"
    gcs_stdout = LOG_DIR / f"{safe}.gcs.stdout.log"
    gcs_stderr = LOG_DIR / f"{safe}.gcs.stderr.log"

    for p in (gcs_status, drone_status, gcs_json, drone_json, gcs_stdout, gcs_stderr):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    gcs_cmd = [
        sys.executable,
        "-u",
        "core/run_proxy.py",
        "gcs",
        "--suite",
        suite_id,
        "--ephemeral",
        "--status-file",
        str(gcs_status),
        "--json-out",
        str(gcs_json),
        "--stop-seconds",
        str(stop_seconds),
    ]

    t0 = time.time()
    with open(gcs_stderr, "w", encoding="utf-8") as err_f:
        gcs_proc = subprocess.Popen(
            gcs_cmd,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=err_f,
            text=True,
            bufsize=1,
        )

        reader = GcsReader(gcs_proc, gcs_stdout)
        reader.start()

        pub_hex = reader.wait_pub(timeout_s=8.0)
        if not pub_hex:
            gcs_stdout_text = _tail_text(gcs_stdout)
            gcs_stderr_text = _tail_text(gcs_stderr)
            classes = _classify_failure(
                passed=False,
                interrupted=False,
                drone_rc=1,
                drone_stdout="",
                drone_stderr="",
                gcs_stdout=gcs_stdout_text,
                gcs_stderr=gcs_stderr_text,
                status_ok=False,
                pubkey_ready=False,
            )
            try:
                gcs_proc.kill()
            except Exception:
                pass
            try:
                gcs_proc.wait(timeout=5)
            except Exception:
                pass
            return {
                "suite": suite_id,
                "pass": False,
                "primary_class": classes["primary_class"],
                "secondary_class": classes["secondary_class"],
                "failure_phase": classes["failure_phase"],
                "elapsed_s": round(time.time() - t0, 3),
                "error": "gcs did not expose ephemeral public key",
                "status_ok": False,
                "gcs_stdout_log": str(gcs_stdout),
                "gcs_stderr_log": str(gcs_stderr),
                "gcs_stdout_tail": gcs_stdout_text[-1200:],
                "gcs_stderr_tail": gcs_stderr_text[-1200:],
            }

        drone_cmd = [
            sys.executable,
            "-u",
            "core/run_proxy.py",
            "drone",
            "--suite",
            suite_id,
            "--gcs-pub-hex",
            pub_hex,
            "--status-file",
            str(drone_status),
            "--json-out",
            str(drone_json),
            "--stop-seconds",
            str(stop_seconds),
        ]

        drone_proc = subprocess.run(
            drone_cmd,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=stop_seconds + 25,
        )

        try:
            gcs_proc.wait(timeout=stop_seconds + 25)
        except subprocess.TimeoutExpired:
            gcs_proc.kill()
            gcs_proc.wait(timeout=10)

    elapsed_s = round(time.time() - t0, 3)
    gcs_text = ""
    gcs_err_text = ""
    try:
        gcs_text = gcs_stdout.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        gcs_err_text = gcs_stderr.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass

    drone_ok = "PQC handshake completed successfully" in (drone_proc.stdout or "")
    gcs_ok = "PQC handshake completed successfully" in gcs_text

    status_ok = False
    status_error = ""
    try:
        gs = json.loads(gcs_status.read_text(encoding="utf-8"))
        ds = json.loads(drone_status.read_text(encoding="utf-8"))
        g_suite = gs.get("suite")
        d_suite = ds.get("suite")
        g_hs = bool(gs.get("counters", {}).get("handshake_metrics"))
        d_hs = bool(ds.get("counters", {}).get("handshake_metrics"))
        status_ok = (g_suite == suite_id) and (d_suite == suite_id) and g_hs and d_hs
        if not status_ok:
            status_error = f"status mismatch g_suite={g_suite} d_suite={d_suite} g_hs={g_hs} d_hs={d_hs}"
    except Exception as exc:
        status_error = f"status parse error: {exc}"

    passed = bool(
        drone_proc.returncode == 0
        and drone_ok
        and gcs_ok
        and status_ok
    )

    classes = _classify_failure(
        passed=passed,
        interrupted=False,
        drone_rc=drone_proc.returncode,
        drone_stdout=drone_proc.stdout or "",
        drone_stderr=drone_proc.stderr or "",
        gcs_stdout=gcs_text,
        gcs_stderr=gcs_err_text,
        status_ok=status_ok,
        pubkey_ready=True,
    )
    if classes["primary_class"] not in PRIMARY_CLASSES:
        classes["primary_class"] = "handshake-verify-fail"

    return {
        "suite": suite_id,
        "pass": passed,
        "primary_class": classes["primary_class"],
        "secondary_class": classes["secondary_class"],
        "failure_phase": classes["failure_phase"],
        "elapsed_s": elapsed_s,
        "drone_returncode": drone_proc.returncode,
        "drone_handshake_log": drone_ok,
        "gcs_handshake_log": gcs_ok,
        "status_ok": status_ok,
        "status_error": status_error,
        "error": "" if passed else "handshake evidence incomplete",
        "drone_stdout_tail": (drone_proc.stdout or "")[-1200:],
        "drone_stderr_tail": (drone_proc.stderr or "")[-1200:],
        "gcs_stdout_tail": gcs_text[-1200:],
        "gcs_stderr_tail": gcs_err_text[-1200:],
        "gcs_stdout_log": str(gcs_stdout),
        "gcs_stderr_log": str(gcs_stderr),
    }


def _write_summary(suites: list[str], results: list[dict], interrupted: bool) -> Path:
    passed = sum(1 for r in results if r.get("pass"))
    failed = len(results) - passed

    class_counts: Dict[str, int] = {cls: 0 for cls in sorted(PRIMARY_CLASSES)}
    startup_failures = 0
    protocol_failures = 0
    for result in results:
        cls = str(result.get("primary_class", "handshake-verify-fail"))
        if cls not in class_counts:
            class_counts[cls] = 0
        class_counts[cls] += 1
        phase = str(result.get("failure_phase", "")).lower()
        if phase == "startup":
            startup_failures += 1
        elif phase == "protocol":
            protocol_failures += 1

    command_block = {
        "python": sys.executable,
        "cwd": str(ROOT),
        "env_overrides": {
            "PYTHONPATH": ".",
            "DRONE_HOST": "127.0.0.1",
            "GCS_HOST": "127.0.0.1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
        },
        "gcs_cmd_template": [
            sys.executable,
            "-u",
            "core/run_proxy.py",
            "gcs",
            "--suite",
            "<suite_id>",
            "--ephemeral",
            "--status-file",
            str(LOG_DIR / "<suite>.gcs.status.json"),
            "--json-out",
            str(LOG_DIR / "<suite>.gcs.counters.json"),
            "--stop-seconds",
            "14",
        ],
        "drone_cmd_template": [
            sys.executable,
            "-u",
            "core/run_proxy.py",
            "drone",
            "--suite",
            "<suite_id>",
            "--gcs-pub-hex",
            "<captured_pub_hex>",
            "--status-file",
            str(LOG_DIR / "<suite>.drone.status.json"),
            "--json-out",
            str(LOG_DIR / "<suite>.drone.counters.json"),
            "--stop-seconds",
            "14",
        ],
    }

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "suite_count": len(suites),
        "executed": len(results),
        "passed": passed,
        "failed": failed,
        "interrupted": interrupted,
        "class_counts": class_counts,
        "startup_failures": startup_failures,
        "protocol_failures": protocol_failures,
        "command_reproducibility": command_block,
        "results": results,
    }
    report_path = LOG_DIR / "summary.json"
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return report_path


def main() -> int:
    suites = list_runtime_suites()
    print(f"[INFO] Runtime suite count: {len(suites)}")

    results = []
    interrupted = False
    try:
        for i, suite in enumerate(suites, start=1):
            print(f"[{i:02d}/{len(suites)}] {suite} ...", flush=True)
            res = run_one_suite(suite)
            results.append(res)
            print(
                f"      {'PASS' if res['pass'] else 'FAIL'} elapsed={res['elapsed_s']}s "
                f"class={res.get('primary_class', 'unknown')}"
            )
    except KeyboardInterrupt:
        interrupted = True
        print("\n[WARN] Sweep interrupted by user. Writing partial summary...")

    report_path = _write_summary(suites, results, interrupted=interrupted)
    passed = sum(1 for r in results if r.get("pass"))
    failed = len(results) - passed

    print("\n=== Localhost Handshake Sweep (Ephemeral) Summary ===")
    print(f"passed={passed} failed={failed} executed={len(results)} total={len(suites)}")
    print(f"report={report_path}")
    if interrupted:
        print("status=INTERRUPTED")

    if failed:
        print("\nFailed suites:")
        for r in results:
            if not r["pass"]:
                print(f"- {r['suite']}: {r.get('error') or r.get('status_error')}")

    return 0 if (failed == 0 and not interrupted and len(results) == len(suites)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
