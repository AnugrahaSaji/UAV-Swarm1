import importlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _standard_lib_path() -> Path:
    if sys.platform == "win32":
        return ROOT / "core" / "libasconaead128.dll"
    if sys.platform == "darwin":
        return ROOT / "core" / "libasconaead128.dylib"
    return ROOT / "core" / "libasconaead128.so"


def _build_standard_ascon() -> Path:
    lib_path = _standard_lib_path()
    if lib_path.exists():
        return lib_path
    subprocess.run(
        [sys.executable, "-m", "core.build_ascon_aead128"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return lib_path


def test_standard_ascon_build_script_emits_shared_library():
    lib_path = _build_standard_ascon()
    assert lib_path.exists()


def test_standard_ascon_matches_official_kat_count_1():
    _build_standard_ascon()
    import core.ascon_backend as ascon_native

    ascon_native = importlib.reload(ascon_native)

    key = bytes.fromhex("000102030405060708090A0B0C0D0E0F")
    nonce = bytes.fromhex("101112131415161718191A1B1C1D1E1F")
    ciphertext = ascon_native.encrypt(key, nonce, b"", b"", "Ascon-AEAD128")

    assert ciphertext.hex().upper() == "4F9C278211BEC9316BF68F46EE8B2EC6"
    assert ascon_native.decrypt(key, nonce, b"", ciphertext, "Ascon-AEAD128") == b""


def test_standard_ascon_is_reported_as_available_runtime_aead():
    _build_standard_ascon()
    import core.ascon_backend as ascon_native
    import core.suites as suites

    ascon_native = importlib.reload(ascon_native)
    suites = importlib.reload(suites)
    assert "ascon128" in suites.available_aead_tokens()
