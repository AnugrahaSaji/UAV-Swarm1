from __future__ import annotations

import argparse
import os
import re
import subprocess
from ipaddress import ip_address
from typing import Iterable
from pathlib import Path
import sys

# Ensure repo root is importable even under Python safe-path settings.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False)
        out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
        return p.returncode, out.strip()
    except Exception as exc:
        return 99, f"EXCEPTION: {exc}"


def _is_valid_ip(ip: str) -> bool:
    try:
        ip_address(ip)
        return True
    except ValueError:
        return False


def _parse_ipv4s(text: str) -> list[str]:
    ips = re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", text)
    out: list[str] = []
    for ip in ips:
        if _is_valid_ip(ip) and ip not in out:
            out.append(ip)
    return out


def _local_ipv4_candidates() -> list[str]:
    if os.name == "nt":
        # Prefer a structured query (avoids parsing subnet masks/gateways from ipconfig).
        code, out = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress",
            ]
        )
        ips = _parse_ipv4s(out) if code == 0 else []
        if ips:
            return ips

        # Fallback: parse ipconfig output, but try to target only IPv4 address lines.
        code, out = _run(["ipconfig"])
        if code != 0:
            return []

        targeted = re.findall(r"IPv4 Address[^:]*:\s*(\d{1,3}(?:\.\d{1,3}){3})", out)
        if targeted:
            return [ip for ip in targeted if _is_valid_ip(ip)]

        return _parse_ipv4s(out)

    code, out = _run(["ip", "-4", "addr"])
    if code != 0:
        return []

    ips = re.findall(r"inet\s+(\d{1,3}(?:\.\d{1,3}){3})/\d+", out)
    return [ip for ip in ips if _is_valid_ip(ip)]


def _fmt_list(xs: Iterable[str]) -> str:
    xs = list(xs)
    return ", ".join(xs) if xs else "<none>"


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify GCS/Drone IP consistency for secure-tunnel")
    ap.add_argument("--role", choices=["auto", "gcs", "drone"], default="auto")
    args = ap.parse_args()

    # Importing core.config loads env files via env_loader
    try:
        from core.config import CONFIG
    except Exception as exc:
        print("FAIL: could not import core.config.CONFIG:", exc)
        return 2

    role = args.role
    if role == "auto":
        role = "gcs" if os.name == "nt" else "drone"

    expected_lan = CONFIG.get("GCS_HOST_LAN") if role == "gcs" else CONFIG.get("DRONE_HOST_LAN")
    expected_ts = CONFIG.get("GCS_HOST_TAILSCALE") if role == "gcs" else CONFIG.get("DRONE_HOST_TAILSCALE")

    print("Role:", role)
    print("TUNNEL_HOST_PROFILE:", CONFIG.get("TUNNEL_HOST_PROFILE"))
    print("Expected LAN:", expected_lan)
    print("Expected Tailscale:", expected_ts)

    ok = True
    if not expected_lan or not _is_valid_ip(str(expected_lan)):
        print("FAIL: expected LAN IP is missing/invalid")
        ok = False

    if expected_ts and not _is_valid_ip(str(expected_ts)):
        print("FAIL: expected Tailscale IP is invalid")
        ok = False

    local_ips = _local_ipv4_candidates()
    print("Observed local IPv4 candidates:", _fmt_list(local_ips))

    if expected_lan and str(expected_lan) not in local_ips:
        print("WARN: expected LAN IP not found on this host (check active adapter/interface)")

    if ok:
        print("PASS: config imported and IPs parsed")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
