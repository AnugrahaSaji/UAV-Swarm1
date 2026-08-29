import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from core.process import ManagedProcess
from core.suites import get_suite, normalize_aead_token

from .common import log


ROOT = Path(__file__).resolve().parents[1]
SECRETS_DIR = ROOT / "secrets" / "matrix"
DRONE_LOGS_DIR = ROOT / "logs" / "sscheduler" / "drone"
GCS_LOGS_DIR = ROOT / "logs" / "sscheduler" / "gcs"
DRONE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
GCS_LOGS_DIR.mkdir(parents=True, exist_ok=True)


class DroneProxyManager:
    def __init__(self):
        self.proc: Optional[ManagedProcess] = None
        self.current_suite: Optional[str] = None
        self.current_aead: Optional[str] = None
        self._last_log: Optional[Path] = None
        self._log_handle = None

    def start(self, suite_name: str, *, aead_token: Optional[str] = None) -> bool:
        if self.proc and self.proc.is_running():
            self.stop()

        suite = get_suite(suite_name)
        if not suite:
            log(f"Unknown suite: {suite_name}")
            return False
        resolved_aead = normalize_aead_token(aead_token) if aead_token else str(suite.get("aead_token", "aesgcm"))

        peer_pubkey = SECRETS_DIR / suite_name / "gcs_signing.pub"
        if not peer_pubkey.exists():
            log(f"Missing public key: {peer_pubkey}")
            return False

        cmd = [
            sys.executable,
            "-m",
            "core.run_proxy",
            "drone",
            "--suite",
            suite_name,
            "--aead",
            resolved_aead,
            "--peer-pubkey-file",
            str(peer_pubkey),
            "--quiet",
            "--status-file",
            str(DRONE_LOGS_DIR / "drone_status.json"),
        ]

        ts = time.strftime("%Y%m%d-%H%M%S")
        log_path = DRONE_LOGS_DIR / f"proxy_{suite_name}_{resolved_aead}_{ts}.log"
        log(f"Starting proxy: {suite_name} (aead={resolved_aead})")
        try:
            self._log_handle = open(log_path, "w", encoding="utf-8")
        except Exception:
            self._log_handle = subprocess.DEVNULL

        env = os.environ.copy()
        self.proc = ManagedProcess(
            cmd=cmd,
            name=f"proxy-{suite_name}",
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            env=env,
        )
        if not self.proc.start():
            self._close_log_handle()
            return False

        self._last_log = log_path
        self.current_suite = suite_name
        self.current_aead = resolved_aead
        time.sleep(2.0)
        if not self.proc.is_running():
            log(f"Proxy exited early for {suite_name}")
            return False
        return True

    def stop(self):
        if self.proc:
            self.proc.stop()
            self.proc = None
            self.current_suite = None
            self.current_aead = None
        self._close_log_handle()

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.is_running()

    def _close_log_handle(self):
        if self._log_handle not in (None, subprocess.DEVNULL):
            try:
                self._log_handle.close()
            except Exception:
                pass
        self._log_handle = None


class GcsProxyManager:
    def __init__(self):
        self.managed_proc: Optional[ManagedProcess] = None
        self.current_suite: Optional[str] = None
        self.current_aead: Optional[str] = None
        self._log_handle = None

    def start(self, suite_name: str, *, aead_token: Optional[str] = None) -> bool:
        if self.managed_proc and self.managed_proc.is_running():
            self.stop()

        suite = get_suite(suite_name)
        if not suite:
            log(f"Unknown suite: {suite_name}")
            return False
        resolved_aead = normalize_aead_token(aead_token) if aead_token else str(suite.get("aead_token", "aesgcm"))

        secret_dir = SECRETS_DIR / suite_name
        gcs_key = secret_dir / "gcs_signing.key"
        if not gcs_key.exists():
            log(f"Missing signing key: {gcs_key}")
            return False

        cmd = [
            sys.executable,
            "-m",
            "core.run_proxy",
            "gcs",
            "--suite",
            suite_name,
            "--aead",
            resolved_aead,
            "--gcs-secret-file",
            str(gcs_key),
            "--quiet",
        ]

        ts = time.strftime("%Y%m%d-%H%M%S")
        log_path = GCS_LOGS_DIR / f"proxy_{suite_name}_{resolved_aead}_{ts}.log"
        log(f"Starting GCS proxy: {suite_name} (aead={resolved_aead})")
        try:
            self._log_handle = open(log_path, "w", encoding="utf-8")
        except Exception:
            self._log_handle = subprocess.DEVNULL

        env = os.environ.copy()
        self.managed_proc = ManagedProcess(
            cmd=cmd,
            name=f"proxy-{suite_name}",
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            env=env,
        )
        if not self.managed_proc.start():
            self._close_log_handle()
            return False

        self.current_suite = suite_name
        self.current_aead = resolved_aead
        time.sleep(2.0)
        if not self.managed_proc.is_running():
            log(f"GCS proxy exited early for {suite_name}")
            return False
        return True

    def stop(self):
        if self.managed_proc:
            self.managed_proc.stop()
            self.managed_proc = None
            self.current_suite = None
            self.current_aead = None
        self._close_log_handle()

    def is_running(self) -> bool:
        return self.managed_proc is not None and self.managed_proc.is_running()

    def _close_log_handle(self):
        if self._log_handle not in (None, subprocess.DEVNULL):
            try:
                self._log_handle.close()
            except Exception:
                pass
        self._log_handle = None
