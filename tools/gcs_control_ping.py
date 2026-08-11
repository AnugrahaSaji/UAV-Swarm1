#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--cmd", default="ping")
    p.add_argument("--suite", default=None)
    args = p.parse_args()

    req = {"cmd": args.cmd}
    if args.suite is not None:
        req["suite"] = args.suite
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5.0)
    s.connect((args.host, args.port))
    s.sendall(json.dumps(req).encode() + b"\n")
    data = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break
    s.close()
    print(data.decode(errors="replace").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
