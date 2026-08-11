"""Verify the standardized Ascon-AEAD128 backend against official KATs."""

from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
KAT_FILE = ROOT / "third_party" / "ascon_c_sp800_232" / "crypto_aead" / "asconaead128" / "LWC_AEAD_KAT_128_128.txt"

LIB_NAMES = {
    "Windows": "libasconaead128.dll",
    "Linux": "libasconaead128.so",
    "Darwin": "libasconaead128.dylib",
}
LIB_PATH = HERE / LIB_NAMES.get(platform.system(), "libasconaead128.so")


def _build_if_needed() -> None:
    if LIB_PATH.exists():
        return
    subprocess.run([sys.executable, "-m", "core.build_ascon_aead128"], cwd=ROOT, check=True)


def _parse_kat(limit: int = 8) -> list[dict[str, bytes]]:
    cases: list[dict[str, bytes]] = []
    current: dict[str, bytes] = {}

    with KAT_FILE.open("r", encoding="ascii") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                if current:
                    cases.append(current)
                    current = {}
                    if len(cases) >= limit:
                        break
                continue
            if " = " in line:
                key, value = line.split(" = ", 1)
            elif " =" in line:
                key, value = line.split(" =", 1)
                value = value.lstrip()
            else:
                continue
            if key == "Count":
                continue
            current[key] = bytes.fromhex(value) if value else b""

    if current and len(cases) < limit:
        cases.append(current)
    return cases


def main() -> int:
    _build_if_needed()
    lib = ctypes.CDLL(str(LIB_PATH))

    lib.asconaead128_encrypt.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_uint64,
        ctypes.c_char_p,
        ctypes.c_uint64,
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    lib.asconaead128_encrypt.restype = ctypes.c_int

    lib.asconaead128_decrypt.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_uint64,
        ctypes.c_char_p,
        ctypes.c_uint64,
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    lib.asconaead128_decrypt.restype = ctypes.c_int

    for index, case in enumerate(_parse_kat(), start=1):
        plaintext = case["PT"]
        ciphertext = case["CT"]
        tag_buf = ctypes.create_string_buffer(16)
        ct_buf = ctypes.create_string_buffer(len(plaintext))
        rc = lib.asconaead128_encrypt(
            tag_buf,
            ct_buf,
            plaintext,
            ctypes.c_uint64(len(plaintext)),
            case["AD"],
            ctypes.c_uint64(len(case["AD"])),
            case["Nonce"],
            case["Key"],
        )
        if rc != 0:
            raise SystemExit(f"encryption failed for KAT case {index}")
        observed = ct_buf.raw + tag_buf.raw
        if observed != ciphertext:
            raise SystemExit(
                f"KAT mismatch at case {index}: expected {ciphertext.hex().upper()} got {observed.hex().upper()}"
            )

        pt_buf = ctypes.create_string_buffer(max(len(plaintext), 1))
        rc = lib.asconaead128_decrypt(
            pt_buf,
            ciphertext[-16:],
            ciphertext[:-16],
            ctypes.c_uint64(len(ciphertext) - 16),
            case["AD"],
            ctypes.c_uint64(len(case["AD"])),
            case["Nonce"],
            case["Key"],
        )
        if rc != 0 or pt_buf.raw[: len(plaintext)] != plaintext:
            raise SystemExit(f"decryption failed for KAT case {index}")

    print(f"verified {index} Ascon-AEAD128 KAT cases with {LIB_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
