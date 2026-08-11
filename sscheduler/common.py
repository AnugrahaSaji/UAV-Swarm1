import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def resolve_benchmark_mode(cli_value: Optional[str], default_mode: str) -> str:
    def _norm(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None

    cli_mode = _norm(cli_value)
    env_mode = _norm(os.getenv("BENCHMARK_MODE"))
    default = _norm(default_mode)
    allowed = {"MAVPROXY"}

    if cli_mode and cli_mode not in allowed:
        raise ValueError(f"Invalid --mode '{cli_mode}', must be MAVPROXY")
    if env_mode and env_mode not in allowed:
        raise ValueError(f"Invalid BENCHMARK_MODE '{env_mode}', must be MAVPROXY")
    if default and default not in allowed:
        raise ValueError(f"Invalid default benchmark mode '{default}', must be MAVPROXY")
    if cli_mode and env_mode and cli_mode != env_mode:
        raise RuntimeError(f"BENCHMARK_MODE conflict: cli={cli_mode} env={env_mode}")

    return cli_mode or env_mode or default


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [sscheduler] {msg}", flush=True)


def read_handshake_status(timeout: float = 45.0, status_file: Optional[Path] = None) -> Dict[str, Any]:
    target = status_file or (Path(__file__).resolve().parents[1] / "logs" / "sscheduler" / "drone" / "drone_status.json")
    start_time = time.time()

    while time.time() - start_time < timeout:
        if target.exists():
            try:
                with open(target, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                status = data.get("status")
                if status in ("handshake_ok", "running"):
                    metrics = data.get("handshake_metrics")
                    if not metrics:
                        counters = data.get("counters", {})
                        metrics = counters.get("handshake_metrics", {})
                    if metrics:
                        data["handshake_metrics"] = metrics
                        data["status"] = "handshake_ok"
                        return data
            except Exception:
                pass
        time.sleep(0.2)

    return {"status": "timeout", "handshake_metrics": {}}
