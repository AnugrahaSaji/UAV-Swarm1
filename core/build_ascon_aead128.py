"""Build the standardized Ascon-AEAD128 shared library.

This compiles the vendored SP 800-232-compatible `ascon/ascon-c` `opt64`
implementation into a small shared library consumed by `core.ascon_backend`.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VENDOR = ROOT / "third_party" / "ascon_c_sp800_232"
IMPL_DIR = VENDOR / "crypto_aead" / "asconaead128" / "opt64"
TESTS_DIR = VENDOR / "tests"
SOURCE = HERE / "_ascon_aead128_shlib.c"


def _output_path() -> Path:
    system = platform.system()
    if system == "Windows":
        return HERE / "libasconaead128.dll"
    if system == "Darwin":
        return HERE / "libasconaead128.dylib"
    return HERE / "libasconaead128.so"


def _compiler() -> str:
    configured = os.environ.get("CC")
    if configured and shutil.which(configured):
        return configured

    if platform.system() == "Windows":
        candidates = [
            r"C:\Strawberry\c\bin\gcc.exe",
            r"C:\mingw64\bin\gcc.exe",
            "x86_64-w64-mingw32-gcc",
            "gcc",
        ]
        for candidate in candidates:
            resolved = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
            if not resolved:
                continue
            try:
                probe = subprocess.run(
                    [resolved, "-dumpmachine"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except Exception:
                continue
            machine = probe.stdout.strip().lower()
            if "x86_64" in machine or "amd64" in machine:
                return resolved
        raise SystemExit("no 64-bit GCC found for Windows Ascon build")

    compiler = shutil.which("gcc")
    if compiler:
        return compiler
    raise SystemExit("compiler not found: gcc")


def _build_command(output: Path) -> list[str]:
    command = [
        _compiler(),
        "-O3",
        "-shared",
        "-o",
        str(output),
        str(SOURCE),
        f"-I{IMPL_DIR}",
        f"-I{TESTS_DIR}",
        "-Wall",
    ]
    if platform.system() != "Windows":
        command.insert(3, "-fPIC")
    return command


def build() -> Path:
    missing = [path for path in (SOURCE, IMPL_DIR, TESTS_DIR) if not path.exists()]
    if missing:
        raise SystemExit(f"missing Ascon source inputs: {', '.join(str(path) for path in missing)}")

    output = _output_path()
    command = _build_command(output)
    subprocess.run(command, cwd=ROOT, check=True)
    return output


def main() -> int:
    output = build()
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
