#!/usr/bin/env python3
from __future__ import annotations

import argparse


def try_read(busnum: int, address: int, shunt_ohms: float, max_expected_amps: float) -> dict:
    from ina219 import INA219

    ina = INA219(shunt_ohms=shunt_ohms, address=address, busnum=busnum, max_expected_amps=max_expected_amps)
    ina.configure()
    return {
        "busnum": busnum,
        "address": hex(address),
        "voltage_v": float(ina.voltage()),
        "current_ma": float(ina.current()),
        "power_mw": float(ina.power()),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--bus", type=int, action="append", default=[1, 20, 21])
    p.add_argument("--addr", type=lambda s: int(s, 0), action="append", default=[0x40])
    p.add_argument("--shunt-ohms", type=float, default=0.1)
    p.add_argument("--max-amps", type=float, default=3.0)
    args = p.parse_args()

    errors: list[str] = []
    for busnum in args.bus:
        for addr in args.addr:
            try:
                reading = try_read(busnum, addr, args.shunt_ohms, args.max_amps)
                print("OK", reading)
                return 0
            except Exception as e:
                errors.append(f"bus={busnum} addr={hex(addr)} -> {e}")

    print("FAILED")
    for line in errors:
        print(" ", line)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
