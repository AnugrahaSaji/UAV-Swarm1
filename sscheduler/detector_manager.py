"""
DDoS Detector Process Manager (Axis 3)
=======================================
Manages the lifecycle of DDoS detection subprocesses on the drone.

Detectors run as standalone Python scripts that sniff MAVLink packets
and produce live predictions:
  - XGBoost: ddos/xgb.py  (fast, 54-feature, ~10 s warmup)
  - TST:     ddos/tst.py   (TransformerIDS, 46-feature, ~5 s warmup)

Both require root (for raw packet capture via scapy) and should run
under the scheduler's active Python environment unless an explicit
interpreter override is configured.

Architecture
~~~~~~~~~~~~
- Only ONE detector runs at a time (resource constraint).
- DetectorManager tracks: current level, subprocess PID, warmup state.
- The scheduler's EnergyAwarePolicy issues UPGRADE_DETECTOR /
  DOWNGRADE_DETECTOR actions; the scheduler loop calls set_level()
  which stops the old detector and starts the new one.
- Graceful shutdown via SIGTERM with SIGKILL fallback.
"""

import logging
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Optional

logger = logging.getLogger("sscheduler.detector")

# ── Configuration ────────────────────────────────────────────────────

# Path to the ddos/ directory relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DDOS_DIR = _PROJECT_ROOT / "ddos"

# Detector scripts
_DETECTOR_SCRIPTS = {
    "LGBM": DDOS_DIR / "lgbm.py",
    "RF": DDOS_DIR / "rf.py",
    "XGBOOST": DDOS_DIR / "xgb.py",
    "TST": DDOS_DIR / "tst.py",
}

def _resolve_python_interpreter(candidate: Optional[str]) -> str:
    """Resolve an interpreter path or executable name into a runnable command."""
    value = str(candidate or "").strip()
    if not value:
        return ""
    expanded = os.path.expanduser(value)
    if os.path.isabs(expanded):
        return expanded if os.path.exists(expanded) else ""
    located = shutil.which(expanded)
    return located or expanded


def _default_detector_python() -> str:
    """Pick the detector interpreter from override, active Python, then PATH."""
    override = os.environ.get("DETECTOR_PYTHON", "").strip()
    for candidate in (
        override,
        sys.executable,
        shutil.which("python3"),
        shutil.which("python"),
    ):
        resolved = _resolve_python_interpreter(candidate)
        if resolved:
            return resolved
    return ""


DETECTOR_PYTHON = _default_detector_python()

# Warmup durations (seconds) — detector needs this long before
# producing reliable predictions
_WARMUP_S = {
    "NONE": 0.0,
    "LGBM": 5.0,          # model load + first window (~100 pkts)
    "RF": 15.0,           # larger model load (~200 MB) + first window
    "XGBOOST": 10.0,      # model load (~33 MB) + first window
    "TST": 5.0,           # TransformerIDS loads in ~0.05 s, allow settle time
}

# Grace period for SIGTERM before escalating to SIGKILL
_TERM_TIMEOUT_S = 5.0


class DetectorLevel(str, Enum):
    """Mirror of policy.DetectorLevel for import convenience."""
    NONE = "NONE"
    LGBM = "LGBM"
    RF = "RF"
    XGBOOST = "XGBOOST"
    TST = "TST"


class DetectorManager:
    """Manages DDoS detector subprocess lifecycle.

    Thread-safe: all state mutations are guarded by a lock.

    Usage from sdrone.py::

        dm = DetectorManager()
        dm.set_level("XGBOOST")   # starts XGBoost detector
        dm.set_level("NONE")      # stops detector
        dm.cleanup()              # ensure cleanup on shutdown
    """

    def __init__(self, python_path: Optional[str] = None,
                 ddos_dir: Optional[Path] = None):
        self._lock = RLock()
        self._python = _resolve_python_interpreter(python_path) or DETECTOR_PYTHON
        self._ddos_dir = ddos_dir or DDOS_DIR
        self._process: Optional[subprocess.Popen] = None
        self._current_level: str = DetectorLevel.NONE.value
        self._start_mono: float = 0.0  # monotonic time when started
        self._err_fh = None
        self._out_fh = None

    @property
    def current_level(self) -> str:
        """Current detector level (NONE / XGBOOST / TST)."""
        with self._lock:
            return self._current_level

    @property
    def is_running(self) -> bool:
        """True if a detector subprocess is currently alive."""
        with self._lock:
            if self._process is None:
                return False
            return self._process.poll() is None

    @property
    def is_warming_up(self) -> bool:
        """True if the detector is running but still in warmup phase."""
        if not self.is_running:
            return False
        elapsed = time.monotonic() - self._start_mono
        warmup = _WARMUP_S.get(self._current_level, 0.0)
        return elapsed < warmup

    @property
    def warmup_remaining_s(self) -> float:
        """Seconds remaining in warmup, or 0 if warmup is complete."""
        if not self.is_running:
            return 0.0
        elapsed = time.monotonic() - self._start_mono
        warmup = _WARMUP_S.get(self._current_level, 0.0)
        return max(0.0, warmup - elapsed)

    def set_level(self, target_level: str) -> bool:
        """Switch to the specified detector level.

        - If target is NONE, stops any running detector.
        - If target is different from current, stops current and starts new.
        - If target is same as current and detector is running, no-op.

        Returns True if the transition was successful.
        """
        target_level = target_level.upper()
        if target_level not in ("NONE", "LGBM", "RF", "XGBOOST", "TST"):
            logger.error(f"Unknown detector level: {target_level}")
            return False

        with self._lock:
            if target_level == self._current_level and self.is_running:
                logger.debug(f"Detector already at {target_level}")
                return True

            # Stop current detector if running
            self._stop_locked()

            if target_level == DetectorLevel.NONE.value:
                self._current_level = DetectorLevel.NONE.value
                logger.info("Detector level set to NONE (no detection)")
                return True

            # Start new detector
            success = self._start_locked(target_level)
            if success:
                self._current_level = target_level
                self._start_mono = time.monotonic()
                warmup = _WARMUP_S.get(target_level, 0.0)
                logger.info(
                    f"Detector level set to {target_level} "
                    f"(PID {self._process.pid}, warmup={warmup:.0f}s)"
                )
            else:
                self._current_level = DetectorLevel.NONE.value
                logger.error(f"Failed to start {target_level} detector")

            return success

    def _start_locked(self, level: str) -> bool:
        """Start a detector subprocess (must hold self._lock)."""
        script = _DETECTOR_SCRIPTS.get(level)
        if level == "XGBOOST":
            override = os.environ.get("DETECTOR_XGBOOST_SCRIPT", "").strip()
            if override:
                candidate = Path(override)
                script = candidate if candidate.is_absolute() else self._ddos_dir / override
        if script is None or not script.exists():
            logger.error(f"Detector script not found: {script}")
            return False

        # Check if Python interpreter exists
        if not self._python:
            logger.error(f"Detector Python not found: {self._python}")
            return False

        label = level.lower()
        err_path = Path(tempfile.gettempdir()) / f"detector_{label}.err"
        out_path = Path(tempfile.gettempdir()) / f"detector_{label}.out"
        try:
            self._err_fh = open(err_path, "w")
        except Exception:
            self._err_fh = None
        try:
            self._out_fh = open(out_path, "w")
        except Exception:
            self._out_fh = None

        cmd = [self._python, "-u", str(script)]
        iface = os.environ.get("DETECTOR_IFACE", "").strip()
        window = os.environ.get("DETECTOR_WINDOW", "").strip()
        threshold = os.environ.get("DETECTOR_THRESHOLD", "").strip()
        if iface:
            cmd.extend(["--iface", iface])
        if window:
            cmd.extend(["--window", window])
        if threshold:
            cmd.extend(["--threshold", threshold])
        if level == "TST":
            warmup_iterations = os.environ.get(
                "DETECTOR_TST_WARMUP_ITERATIONS", ""
            ).strip()
            metrics_path = os.environ.get(
                "DETECTOR_TST_METRICS_PATH", ""
            ).strip()
            inference_log = os.environ.get(
                "DETECTOR_TST_INFERENCE_LOG", ""
            ).strip()
            if warmup_iterations:
                cmd.extend(["--warmup-iterations", warmup_iterations])
            if metrics_path:
                cmd.extend(["--metrics-path", metrics_path])
            if inference_log:
                cmd.extend(["--inference-log", inference_log])
        if os.environ.get("DETECTOR_USE_SUDO", "").strip().lower() in {"1", "true", "yes", "on"}:
            cmd = ["sudo", "-n", *cmd]
        logger.info(f"Starting {level} detector: {' '.join(cmd)}")

        try:
            kwargs = {
                "stdout": self._out_fh or subprocess.DEVNULL,
                "stderr": self._err_fh or subprocess.DEVNULL,
            }
            # On Linux, use setsid for clean process group management
            if hasattr(os, "setpgrp"):
                kwargs["preexec_fn"] = os.setpgrp

            self._process = subprocess.Popen(cmd, **kwargs)
        except Exception as e:
            logger.error(f"Failed to start {level} detector: {e}")
            if self._err_fh:
                self._err_fh.close()
                self._err_fh = None
            if self._out_fh:
                self._out_fh.close()
                self._out_fh = None
            return False

        # Brief check that the process didn't immediately crash
        time.sleep(2.0)
        if self._process.poll() is not None:
            rc = self._process.returncode
            logger.error(f"{level} detector exited immediately (rc={rc})")
            # Read error output for diagnostics
            if self._err_fh:
                self._err_fh.close()
                self._err_fh = None
                try:
                    err_text = err_path.read_text().strip()
                    if err_text:
                        for line in err_text.splitlines()[-5:]:
                            logger.error(f"  {level} stderr: {line}")
                except Exception:
                    pass
            if self._out_fh:
                self._out_fh.close()
                self._out_fh = None
            self._process = None
            return False

        return True

    def _stop_locked(self) -> None:
        """Stop the current detector subprocess (must hold self._lock)."""
        proc = self._process
        if proc is None:
            return

        if proc.poll() is not None:
            # Already dead
            self._process = None
            if self._err_fh:
                self._err_fh.close()
                self._err_fh = None
            if self._out_fh:
                self._out_fh.close()
                self._out_fh = None
            return

        label = self._current_level
        logger.info(f"Stopping {label} detector (PID {proc.pid})")

        # Try graceful SIGTERM via process group
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:
                proc.terminate()
        except (ProcessLookupError, PermissionError):
            pass

        try:
            proc.wait(timeout=_TERM_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            # Escalate to SIGKILL
            logger.warning(f"{label} detector didn't stop gracefully, sending SIGKILL")
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                logger.error(f"Could not kill {label} detector PID {proc.pid}")

        self._process = None
        if self._err_fh:
            self._err_fh.close()
            self._err_fh = None
        if self._out_fh:
            self._out_fh.close()
            self._out_fh = None

        logger.info(f"{label} detector stopped")

    def cleanup(self) -> None:
        """Stop any running detector and clean up resources.

        Called during scheduler shutdown.
        """
        with self._lock:
            self._stop_locked()
            self._current_level = DetectorLevel.NONE.value

    def get_status(self) -> dict:
        """Return a status dict for telemetry/logging."""
        running = self.is_running
        return {
            "level": self._current_level,
            "running": running,
            "warming_up": self.is_warming_up if running else False,
            "warmup_remaining_s": round(self.warmup_remaining_s, 1),
            "pid": self._process.pid if self._process and running else None,
            "uptime_s": round(time.monotonic() - self._start_mono, 1) if running else 0.0,
        }
