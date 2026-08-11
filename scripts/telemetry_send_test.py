#!/usr/bin/env python3
"""Telemetry Sender Doctor (GCS Side).

This script used to send synthetic telemetry packets for connectivity checks.
It has been intentionally removed during repository cleanup.

NOTE: Keep this file import-safe (no side effects at import time) because
`pytest` may discover files matching `*test.py`.
"""

__test__ = False


def main() -> int:
    print(
        "telemetry_send_test removed: synthetic telemetry tooling has been deleted per repository cleanup."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
