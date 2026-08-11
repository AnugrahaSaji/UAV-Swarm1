#!/usr/bin/env python3
"""Scheduler-local MavProxyManager.

Keeps scheduler runtime independent from the optional `tools` package path.
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from pathlib import Path as _Path
from typing import Optional

from core.config import CONFIG
from core.process import ManagedProcess


ROOT = Path(__file__).resolve().parents[1]


def _logs_dir_for(role: str) -> Path:
    directory = ROOT / "logs" / "sscheduler" / role
    directory.mkdir(parents=True, exist_ok=True)
    return directory


class MavProxyManager:
    def __init__(self, role: str = "generic") -> None:
        self.role = role
        self.managed_proc: Optional[ManagedProcess] = None
        self._last_log: Optional[Path] = None

    def start(self, master_str_or_listen_host, master_baud_or_listen_port, out_ip=None, out_port=None, extra_args=None) -> bool:
        if out_ip is None and out_port is None:
            listen_host = str(master_str_or_listen_host)
            listen_port = int(master_baud_or_listen_port)
            master_str = f"udpin:{listen_host}:{listen_port}"
            out_ip = "127.0.0.1"
            out_port = listen_port
        else:
            master_str = str(master_str_or_listen_host)

        if extra_args is None:
            extra_args = []

        configured = CONFIG.get("MAVPROXY_BINARY")
        out_arg = f"udp:{out_ip}:{int(out_port)}"

        python_exe = sys.executable
        bin_dir = os.path.dirname(python_exe)
        mavproxy_script = os.path.join(bin_dir, "mavproxy.py")

        if os.path.exists(mavproxy_script):
            base_cmd = [python_exe, mavproxy_script]
        elif configured and _Path(str(configured)).exists() and str(configured).lower().endswith(".py"):
            base_cmd = [python_exe, str(configured)]
        elif sys.platform.startswith("win"):
            base_cmd = [python_exe, "-m", "MAVProxy.mavproxy"]
        else:
            base_cmd = ["mavproxy.py"]

        cmd = base_cmd + [f"--master={master_str}", f"--out={out_arg}", "--dialect=ardupilotmega", "--nowait"]
        if extra_args:
            cmd.extend(extra_args)

        log_dir = _logs_dir_for(self.role)
        ts_now = time.strftime("%Y%m%d-%H%M%S")
        log_path = log_dir / f"mavproxy_{self.role}_{ts_now}.log"

        try:
            log_fh = open(log_path, "w", encoding="utf-8")

            stdout_arg = log_fh
            stderr_arg = subprocess.STDOUT
            if sys.platform == "win32":
                stdout_arg = None
                stderr_arg = None

            env = os.environ.copy()
            env["TERM"] = "dumb"

            self.managed_proc = ManagedProcess(
                cmd=cmd,
                name=f"mavproxy-{self.role}",
                stdin=None if sys.platform == "win32" else subprocess.DEVNULL,
                stdout=stdout_arg,
                stderr=stderr_arg,
                new_console=True,
                env=env,
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