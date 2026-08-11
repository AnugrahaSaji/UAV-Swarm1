#!/usr/bin/env python3
"""Shared MavProxyManager for launching mavproxy subprocesses.

Keeps a minimal API: `start(listen_host, listen_port, peer_host, peer_port) -> bool`,
`stop()`, and `is_running()`.
"""
import signal
from pathlib import Path
import time
import subprocess
from typing import Optional
import sys
import os
from pathlib import Path as _Path

from core.config import CONFIG
from core.process import ManagedProcess


ROOT = Path(__file__).resolve().parents[1]

def _logs_dir_for(role: str) -> Path:
    d = ROOT / "logs" / "sscheduler" / role
    d.mkdir(parents=True, exist_ok=True)
    return d


class MavProxyManager:
    def __init__(self, role: str = "generic") -> None:
        self.role = role
        self.managed_proc: Optional[ManagedProcess] = None
        self._last_log: Optional[Path] = None

    def start(self, master_str_or_listen_host, master_baud_or_listen_port, out_ip=None, out_port=None, extra_args=None) -> bool:
        """Start mavproxy using ManagedProcess."""
        # Backwards compatibility: old callers passed (listen_host, listen_port, peer_host, peer_port)
        if out_ip is None and out_port is None:
            # interpret as old-style
            listen_host = str(master_str_or_listen_host)
            listen_port = int(master_baud_or_listen_port)
            peer_host = None
            peer_port = None
            # We'll require caller to pass peer via extra_args in this case, but try to be helpful
            master_str = f"udpin:{listen_host}:{listen_port}"
            out_ip = "127.0.0.1"
            out_port = listen_port  # fallback
        else:
            master_str = str(master_str_or_listen_host)

        master_baud = master_baud_or_listen_port

        if extra_args is None:
            extra_args = []

        # Determine configured binary or fallback name
        configured = CONFIG.get("MAVPROXY_BINARY")
        # Build base out argument
        out_arg = f"udp:{out_ip}:{int(out_port)}"

        # 1. Determine the path to the python interpreter currently running
        python_exe = sys.executable

        # 2. Find mavproxy.py relative to the python executable
        bin_dir = os.path.dirname(python_exe)
        mavproxy_script = os.path.join(bin_dir, "mavproxy.py")

        # 3. Fallbacks
        if os.path.exists(mavproxy_script):
            base_cmd = [python_exe, mavproxy_script]
        elif configured and _Path(str(configured)).exists() and str(configured).lower().endswith(".py"):
            # If CONFIG points to an explicit .py file, use it via sys.executable
            base_cmd = [python_exe, str(configured)]
        elif sys.platform.startswith("win"):
            # Windows fallback: run as module
            base_cmd = [python_exe, "-m", "MAVProxy.mavproxy"]
        else:
            # Linux / general fallback: rely on executable in PATH
            base_cmd = ["mavproxy.py"]

        # 4. Construct full command with master/out and recommended flags
        cmd = base_cmd + [f"--master={master_str}", f"--out={out_arg}", "--dialect=ardupilotmega", "--nowait"]

        # append any extra args verbatim
        if extra_args:
            cmd.extend(extra_args)

        log_dir = _logs_dir_for(self.role)
        ts_now = time.strftime("%Y%m%d-%H%M%S")
        log_path = log_dir / f"mavproxy_{self.role}_{ts_now}.log"
        
        try:
            # On Windows, we might want a new console for interactive use if requested.
            # But for stability, we default to headless unless debugging.
            # The previous code tried to use CREATE_NEW_CONSOLE on Windows.
            # ManagedProcess supports new_console=True.
            
            # Determine if we want a console. Usually yes for GCS, maybe for Drone.
            # But for "secure-tunnel" stability, headless is safer.
            # Let's stick to headless (redirected logs) for now to ensure we capture output.
            
            log_fh = open(log_path, "w", encoding="utf-8")
            
            stdout_arg = log_fh
            stderr_arg = subprocess.STDOUT
            
            if sys.platform == "win32":
                stdout_arg = None
                stderr_arg = None

            # Add TERM=dumb to environment to avoid prompt_toolkit crash on Windows
            env = os.environ.copy()
            env["TERM"] = "dumb"

            self.managed_proc = ManagedProcess(
                cmd=cmd,
                name=f"mavproxy-{self.role}",
                stdin=None if sys.platform == "win32" else subprocess.DEVNULL,
                stdout=stdout_arg,
                stderr=stderr_arg,
                new_console=True, # Windows requires a console
                env=env
            )
            
            if self.managed_proc.start():
                self._last_log = log_path
                time.sleep(0.5)
                if not self.managed_proc.is_running():
                    return False
                return True
            return False
            
        except Exception:
            return False

    def stop(self) -> None:
        if self.managed_proc:
            self.managed_proc.stop()
            self.managed_proc = None

    def is_running(self) -> bool:
        return self.managed_proc is not None and self.managed_proc.is_running()

    def last_log(self) -> Optional[Path]:
        return self._last_log
