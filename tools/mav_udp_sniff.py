#!/usr/bin/env python3
"""Minimal UDP packet counter for MAVLink-forwarded streams."""

from __future__ import annotations

import argparse
import select
import socket
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--ports", nargs="+", type=int, required=True)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--buf", type=int, default=65535)
    args = parser.parse_args()

    socks: list[tuple[int, socket.socket]] = []
    counts: dict[int, int] = {p: 0 for p in args.ports}

    for port in args.ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((args.host, port))
        s.setblocking(False)
        socks.append((port, s))

    deadline = time.time() + args.duration
    while time.time() < deadline:
        r, _, _ = select.select([s for _, s in socks], [], [], 0.5)
        for s in r:
            try:
                s.recvfrom(args.buf)
            except OSError:
                continue
            for port, ss in socks:
                if ss is s:
                    counts[port] += 1
                    break

    for _, s in socks:
        s.close()

    print("counts", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
