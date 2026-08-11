"""ctypes bindings for the standardized Ascon-AEAD128 shared library."""

from __future__ import annotations

import ctypes
import os
import platform
import sys
from dataclasses import dataclass


_HERE = os.path.dirname(os.path.abspath(__file__))
_SYSTEM = platform.system()

_STANDARD_LIB_NAMES = {
    "Windows": "libasconaead128.dll",
    "Linux": "libasconaead128.so",
    "Darwin": "libasconaead128.dylib",
}
_FUNC_ARGTYPES = [
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_uint64,
    ctypes.c_char_p,
    ctypes.c_uint64,
    ctypes.c_char_p,
    ctypes.c_char_p,
]
_TAG_BYTES = 16


@dataclass(frozen=True)
class _VariantBinding:
    name: str
    path: str
    encrypt_fn: object
    decrypt_fn: object


def _library_path(name_map: dict[str, str]) -> str:
    return os.path.join(_HERE, name_map.get(_SYSTEM, next(iter(name_map.values()))))


def _configure_standard_binding() -> tuple[_VariantBinding | None, str | None]:
    path = _library_path(_STANDARD_LIB_NAMES)
    if not os.path.isfile(path):
        return None, (
            f"Ascon-AEAD128 native library not found at {path}. "
            f"Build it with: {sys.executable} -m core.build_ascon_aead128"
        )

    try:
        lib = ctypes.CDLL(path)
        lib.asconaead128_encrypt.argtypes = _FUNC_ARGTYPES
        lib.asconaead128_encrypt.restype = ctypes.c_int
        lib.asconaead128_decrypt.argtypes = _FUNC_ARGTYPES
        lib.asconaead128_decrypt.restype = ctypes.c_int
    except Exception as exc:
        return None, f"failed to load Ascon-AEAD128 library at {path}: {exc}"

    return _VariantBinding(
        name="Ascon-AEAD128",
        path=path,
        encrypt_fn=lib.asconaead128_encrypt,
        decrypt_fn=lib.asconaead128_decrypt,
    ), None

_STANDARD_BINDING: _VariantBinding | None = None
_STANDARD_REASON: str | None = None


def refresh() -> tuple[str, ...]:
    global _STANDARD_BINDING, _STANDARD_REASON
    _STANDARD_BINDING, _STANDARD_REASON = _configure_standard_binding()
    return available_variants()


def available_variants() -> tuple[str, ...]:
    variants: list[str] = []
    if _STANDARD_BINDING is not None:
        variants.append("Ascon-AEAD128")
    return tuple(variants)


def has_variant(name: str) -> bool:
    return name in available_variants()


def missing_reason(name: str) -> str:
    if name == "Ascon-AEAD128":
        return _STANDARD_REASON or ""
    return f"unknown Ascon variant: {name}"


def _resolve_binding(variant: str) -> _VariantBinding:
    if variant == "Ascon-AEAD128":
        if _STANDARD_BINDING is None:
            refresh()
        if _STANDARD_BINDING is None:
            raise ImportError(_STANDARD_REASON or "Ascon-AEAD128 unavailable")
        return _STANDARD_BINDING
    raise ValueError(f"unknown Ascon variant: {variant}")


def encrypt(
    key: bytes,
    nonce: bytes,
    aad: bytes,
    plaintext: bytes,
    variant: str = "Ascon-AEAD128",
) -> bytes:
    """Encrypt using the requested Ascon variant and return ``ciphertext || tag``."""

    binding = _resolve_binding(variant)
    mlen = len(plaintext)
    ct_buf = ctypes.create_string_buffer(mlen)
    tag_buf = ctypes.create_string_buffer(_TAG_BYTES)

    rc = binding.encrypt_fn(
        tag_buf,
        ct_buf,
        plaintext,
        ctypes.c_uint64(mlen),
        aad,
        ctypes.c_uint64(len(aad)),
        nonce,
        key,
    )
    if rc != 0:
        raise RuntimeError(f"{binding.name} encryption failed")

    return ct_buf.raw + tag_buf.raw


def decrypt(
    key: bytes,
    nonce: bytes,
    aad: bytes,
    ciphertext: bytes,
    variant: str = "Ascon-AEAD128",
) -> bytes | None:
    """Decrypt the requested Ascon variant."""

    if len(ciphertext) < _TAG_BYTES:
        return None

    binding = _resolve_binding(variant)
    pt_len = len(ciphertext) - _TAG_BYTES
    ct_body = ciphertext[:pt_len]
    tag = ciphertext[pt_len:]

    pt_buf = ctypes.create_string_buffer(max(pt_len, 1))
    rc = binding.decrypt_fn(
        pt_buf,
        tag,
        ct_body,
        ctypes.c_uint64(pt_len),
        aad,
        ctypes.c_uint64(len(aad)),
        nonce,
        key,
    )
    if rc != 0:
        return None

    return pt_buf.raw[:pt_len]


refresh()
