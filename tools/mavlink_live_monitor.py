#!/usr/bin/env python3
"""Real-time MAVLink sniff-port monitor using pymavlink."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mavlink_collector import HAS_PYMAVLINK, MavLinkMetricsCollector


def main() -> int:
    parser = argparse.ArgumentParser(description="Live MAVLink sniff-port monitor")
    parser.add_argument("--host", default="127.0.0.1", help="Sniff bind host")
    parser.add_argument("--port", type=int, default=14552, help="Sniff UDP port")
    parser.add_argument("--interval", type=float, default=1.0, help="Print interval in seconds")
    parser.add_argument("--recent", type=int, default=8, help="Recent message count to include")
    parser.add_argument("--jsonl", type=str, help="Optional JSONL export path")
    parser.add_argument("--duration", type=float, default=0.0, help="Optional stop-after duration in seconds")
    args = parser.parse_args()

    if not HAS_PYMAVLINK:
        raise SystemExit("pymavlink is required for tools/mavlink_live_monitor.py")

    collector = MavLinkMetricsCollector(role="gcs")
    collector.start_sniffing(port=args.port, host=args.host)

    if args.jsonl:
        collector.start_live_export(
            args.jsonl,
            interval_s=args.interval,
            recent_messages=args.recent,
            context={"tool": "mavlink_live_monitor"},
        )

    deadline = time.monotonic() + float(args.duration) if args.duration and args.duration > 0 else None

    try:
        while True:
            snapshot = collector.get_live_snapshot(recent_messages=args.recent)
            print(json.dumps(snapshot, indent=2))
            if deadline is not None and time.monotonic() >= deadline:
                break
            time.sleep(max(0.1, float(args.interval)))
    except KeyboardInterrupt:
        pass
    finally:
        collector.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
