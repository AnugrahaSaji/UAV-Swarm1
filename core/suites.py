"""PQC cryptographic suite registry and algorithm ID mapping.

Suite identity model (TLS 1.3): cs-{kem}-{sig}
- KEM + SIG determine key-exchange and authentication identity.
- AEAD is a separate runtime config: cfg["SUITE_AEAD_TOKEN"].
- Changing AEAD alone => HKDF epoch ratchet (no new PQC handshake).
- Changing KEM or SIG => full new PQC handshake required.

24 canonical suites: (kem, sig) pairs at matching NIST levels.

NIST Security Level Reference (per liboqs / FIPS 203/204/205):
- L1: ~AES-128 equivalent security
- L3: ~AES-192 equivalent security
- L5: ~AES-256 equivalent security

Note: ML-DSA-44 is claimed as L2 by liboqs (FIPS 204), but we map it to L1
for practical pairing with L1 KEMs (ML-KEM-512, etc.).
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Dict, Iterable, Mapping, Optional, Tuple
import os

try:
    from core.logging_utils import get_logger as _get_logger
    _logger = _get_logger("pqc")
except Exception:
    import logging as _logging
    _logger = _logging.getLogger("pqc")

try:
    from core.config import CONFIG as _CONFIG
except Exception:
    _CONFIG: dict = {}  # type: ignore[assignment]


def _normalize_alias(value: str) -> str:
    """Normalize alias strings for case- and punctuation-insensitive matching."""
    return "".join(ch for ch in value.lower() if ch.isalnum())


# Suite identity: cs-{kem}-{sig}.  No AEAD in the suite ID.
DEFAULT_SUITE_ID = "cs-mlkem768-mldsa65"
OPERATIONAL_DEFAULT_SUITE_IDS = (
    "cs-mlkem512-mldsa44",
    "cs-mlkem768-mldsa65",
    "cs-mlkem1024-mldsa87",
)


# =============================================================================
# KEM Registry - NIST Levels per liboqs/FIPS203
# ML-KEM-512: L1, ML-KEM-768: L3, ML-KEM-1024: L5
# Classic-McEliece-348864: L1, -460896: L3, -8192128: L5
# HQC-128: L1, HQC-192: L3, HQC-256: L5
# =============================================================================
_KEM_REGISTRY_BASE = {
    "mlkem512": {
        "oqs_name": "ML-KEM-512",
        "token": "mlkem512",
        "nist_level": "L1",
        "kem_id": 1,
        "kem_param_id": 1,
        "aliases": (
            "ML-KEM-512",
            "ml-kem-512",
            "mlkem512",
            "kyber512",
            "kyber-512",
            "kyber_512",
            "Kyber512",
        ),
    },
    "mlkem768": {
        "oqs_name": "ML-KEM-768",
        "token": "mlkem768",
        "nist_level": "L3",
        "kem_id": 1,
        "kem_param_id": 2,
        "aliases": (
            "ML-KEM-768",
            "ml-kem-768",
            "mlkem768",
            "kyber768",
            "kyber-768",
            "kyber_768",
            "Kyber768",
        ),
    },
    "mlkem1024": {
        "oqs_name": "ML-KEM-1024",
        "token": "mlkem1024",
        "nist_level": "L5",
        "kem_id": 1,
        "kem_param_id": 3,
        "aliases": (
            "ML-KEM-1024",
            "ml-kem-1024",
            "mlkem1024",
            "kyber1024",
            "kyber-1024",
            "kyber_1024",
            "Kyber1024",
        ),
    },
    "classicmceliece348864": {
        "oqs_name": "Classic-McEliece-348864",
        "token": "classicmceliece348864",
        "nist_level": "L1",
        "kem_id": 3,
        "kem_param_id": 1,
        "aliases": (
            "Classic-McEliece-348864",
            "classicmceliece-348864",
            "classicmceliece348864",
            "mceliece348864",
        ),
    },
    "classicmceliece460896": {
        "oqs_name": "Classic-McEliece-460896",
        "token": "classicmceliece460896",
        "nist_level": "L3",
        "kem_id": 3,
        "kem_param_id": 2,
        "aliases": (
            "Classic-McEliece-460896",
            "classicmceliece-460896",
            "classicmceliece460896",
            "mceliece460896",
        ),
    },
    "classicmceliece8192128": {
        "oqs_name": "Classic-McEliece-8192128",
        "token": "classicmceliece8192128",
        "nist_level": "L5",
        "kem_id": 3,
        "kem_param_id": 3,
        "aliases": (
            "Classic-McEliece-8192128",
            "classicmceliece-8192128",
            "classicmceliece8192128",
            "mceliece8192128",
        ),
    },
    "hqc128": {
        "oqs_name": "HQC-128",
        "token": "hqc128",
        "nist_level": "L1",
        "kem_id": 5,
        "kem_param_id": 1,
        "aliases": (
            "HQC-128",
            "hqc-128",
            "hqc128",
        ),
    },
    "hqc192": {
        "oqs_name": "HQC-192",
        "token": "hqc192",
        "nist_level": "L3",
        "kem_id": 5,
        "kem_param_id": 2,
        "aliases": (
            "HQC-192",
            "hqc-192",
            "hqc192",
        ),
    },
    "hqc256": {
        "oqs_name": "HQC-256",
        "token": "hqc256",
        "nist_level": "L5",
        "kem_id": 5,
        "kem_param_id": 3,
        "aliases": (
            "HQC-256",
            "hqc-256",
            "hqc256",
        ),
    },
}

_KEM_METADATA: Dict[str, Dict[str, object]] = {
    "mlkem512": {
        "standard_status": "approved",
        "source_standard": "NIST FIPS 203",
        "security_category": "Category 1",
        "operational_class": "runtime_default",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "mlkem768": {
        "standard_status": "approved",
        "source_standard": "NIST FIPS 203",
        "security_category": "Category 3",
        "operational_class": "runtime_default",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "mlkem1024": {
        "standard_status": "approved",
        "source_standard": "NIST FIPS 203",
        "security_category": "Category 5",
        "operational_class": "runtime_default",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "classicmceliece348864": {
        "standard_status": "not_selected",
        "source_standard": "Research candidate (not selected by NIST)",
        "security_category": "Category 1",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
    "classicmceliece460896": {
        "standard_status": "not_selected",
        "source_standard": "Research candidate (not selected by NIST)",
        "security_category": "Category 3",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
    "classicmceliece8192128": {
        "standard_status": "not_selected",
        "source_standard": "Research candidate (not selected by NIST)",
        "security_category": "Category 5",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
    "hqc128": {
        "standard_status": "selected_future",
        "source_standard": "NIST HQC future standardization track",
        "security_category": "Category 1",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
    "hqc192": {
        "standard_status": "selected_future",
        "source_standard": "NIST HQC future standardization track",
        "security_category": "Category 3",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
    "hqc256": {
        "standard_status": "selected_future",
        "source_standard": "NIST HQC future standardization track",
        "security_category": "Category 5",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
}


# =============================================================================
# Signature Registry - NIST Levels per liboqs/FIPS204/FIPS205
# ML-DSA-44: L2 (liboqs), but we use L1 for practical pairing with ML-KEM-512
# ML-DSA-65: L3, ML-DSA-87: L5
# Falcon-512: L1, Falcon-1024: L5 (no L3 variant exists in NIST standards)
# SPHINCS+-128s: L1, SPHINCS+-192s: L3, SPHINCS+-256s: L5
# =============================================================================
_SIG_REGISTRY_BASE = {
    "mldsa44": {
        "oqs_name": "ML-DSA-44",
        "token": "mldsa44",
        "nist_level": "L1",  # Practical: pairs with L1 KEMs; liboqs claims L2
        "sig_id": 1,
        "sig_param_id": 1,
        "aliases": (
            "ML-DSA-44",
            "ml-dsa-44",
            "mldsa44",
            "dilithium2",
            "dilithium-2",
            "Dilithium2",
        ),
    },
    "mldsa65": {
        "oqs_name": "ML-DSA-65",
        "token": "mldsa65",
        "nist_level": "L3",
        "sig_id": 1,
        "sig_param_id": 2,
        "aliases": (
            "ML-DSA-65",
            "ml-dsa-65",
            "mldsa65",
            "dilithium3",
            "dilithium-3",
            "Dilithium3",
        ),
    },
    "mldsa87": {
        "oqs_name": "ML-DSA-87",
        "token": "mldsa87",
        "nist_level": "L5",
        "sig_id": 1,
        "sig_param_id": 3,
        "aliases": (
            "ML-DSA-87",
            "ml-dsa-87",
            "mldsa87",
            "dilithium5",
            "dilithium-5",
            "Dilithium5",
        ),
    },
    # Falcon signatures - NTRU-lattice based, compact signatures
    # Falcon-512: L1, Falcon-1024: L5 (no L3 variant per NIST)
    "falcon512": {
        "oqs_name": "Falcon-512",
        "token": "falcon512",
        "nist_level": "L1",
        "sig_id": 2,
        "sig_param_id": 1,
        "aliases": (
            "Falcon-512",
            "falcon-512",
            "falcon512",
            "Falcon512",
        ),
    },
    "falcon1024": {
        "oqs_name": "Falcon-1024",
        "token": "falcon1024",
        "nist_level": "L5",
        "sig_id": 2,
        "sig_param_id": 2,
        "aliases": (
            "Falcon-1024",
            "falcon-1024",
            "falcon1024",
            "Falcon1024",
        ),
    },
    # SPHINCS+ hash-based signatures (stateless)
    "sphincs128s": {
        "oqs_name": "SPHINCS+-SHA2-128s-simple",
        "token": "sphincs128s",
        "nist_level": "L1",
        "sig_id": 3,
        "sig_param_id": 1,
        "aliases": (
            "SLH-DSA-SHA2-128s",
            "SPHINCS+-SHA2-128s-simple",
            "sphincs+-sha2-128s-simple",
            "sphincs128s",
            "sphincs128s_sha2",
            # Fast variant aliases (f vs s - both map to our s variant)
            "sphincs128f",
            "sphincs128fsha2",
            "sphincs128f_sha2",
            "SPHINCS+128s",
        ),
    },
    "sphincs192s": {
        "oqs_name": "SPHINCS+-SHA2-192s-simple",
        "token": "sphincs192s",
        "nist_level": "L3",
        "sig_id": 3,
        "sig_param_id": 2,
        "aliases": (
            "SLH-DSA-SHA2-192s",
            "SPHINCS+-SHA2-192s-simple",
            "sphincs+-sha2-192s-simple",
            "sphincs192s",
            "sphincs192s_sha2",
            "sphincs192f",
            "sphincs192fsha2",
            "sphincs192f_sha2",
            "SPHINCS+192s",
        ),
    },
    "sphincs256s": {
        "oqs_name": "SPHINCS+-SHA2-256s-simple",
        "token": "sphincs256s",
        "nist_level": "L5",
        "sig_id": 3,
        "sig_param_id": 3,
        "aliases": (
            "SLH-DSA-SHA2-256s",
            "SPHINCS+-SHA2-256s-simple",
            "sphincs+-sha2-256s-simple",
            "sphincs256s",
            "sphincs256s_sha2",
            # Fast variant aliases
            "sphincs256f",
            "sphincs256fsha2",
            "sphincs256f_sha2",
            "SPHINCS+256s",
        ),
    },
}

_SIG_METADATA: Dict[str, Dict[str, object]] = {
    "mldsa44": {
        "standard_status": "approved",
        "source_standard": "NIST FIPS 204",
        "security_category": "Category 2",
        "operational_class": "runtime_default",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "mldsa65": {
        "standard_status": "approved",
        "source_standard": "NIST FIPS 204",
        "security_category": "Category 3",
        "operational_class": "runtime_default",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "mldsa87": {
        "standard_status": "approved",
        "source_standard": "NIST FIPS 204",
        "security_category": "Category 5",
        "operational_class": "runtime_default",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "falcon512": {
        "standard_status": "future_track",
        "source_standard": "NIST FN-DSA standardization track",
        "security_category": "Category 1",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
    "falcon1024": {
        "standard_status": "future_track",
        "source_standard": "NIST FN-DSA standardization track",
        "security_category": "Category 5",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
    "sphincs128s": {
        "standard_status": "approved",
        "source_standard": "NIST FIPS 205",
        "security_category": "Category 1",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
    "sphincs192s": {
        "standard_status": "approved",
        "source_standard": "NIST FIPS 205",
        "security_category": "Category 3",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
    "sphincs256s": {
        "standard_status": "approved",
        "source_standard": "NIST FIPS 205",
        "security_category": "Category 5",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
}


_AEAD_REGISTRY_BASE = {
    "aesgcm128": {
        "display_name": "AES-128-GCM",
        "token": "aesgcm128",
        "kdf": "HKDF-SHA256",
        "aliases": (
            "AES-128-GCM",
            "aes-128-gcm",
            "aesgcm128",
            "aes128gcm",
            "AESGCM128",
        ),
    },
    "aesgcm192": {
        "display_name": "AES-192-GCM",
        "token": "aesgcm192",
        "kdf": "HKDF-SHA256",
        "aliases": (
            "AES-192-GCM",
            "aes-192-gcm",
            "aesgcm192",
            "aes192gcm",
            "AESGCM192",
        ),
    },
    "aesgcm256": {
        "display_name": "AES-256-GCM",
        "token": "aesgcm256",
        "kdf": "HKDF-SHA256",
        "aliases": (
            "AES-256-GCM",
            "aes-256-gcm",
            "aesgcm256",
            "aes256gcm",
            "aesgcm",
            "aes-gcm",
            "AESGCM",
        ),
    },
    "aesccm128": {
        "display_name": "AES-128-CCM",
        "token": "aesccm128",
        "kdf": "HKDF-SHA256",
        "aliases": (
            "AES-128-CCM",
            "aes-128-ccm",
            "aesccm128",
            "aes128ccm",
            "AESCCM128",
        ),
    },
    "aesccm192": {
        "display_name": "AES-192-CCM",
        "token": "aesccm192",
        "kdf": "HKDF-SHA256",
        "aliases": (
            "AES-192-CCM",
            "aes-192-ccm",
            "aesccm192",
            "aes192ccm",
            "AESCCM192",
        ),
    },
    "aesccm256": {
        "display_name": "AES-256-CCM",
        "token": "aesccm256",
        "kdf": "HKDF-SHA256",
        "aliases": (
            "AES-256-CCM",
            "aes-256-ccm",
            "aesccm256",
            "aes256ccm",
            "aesccm",
            "aes-ccm",
            "AESCCM",
        ),
    },
    "chacha20poly1305": {
        "display_name": "ChaCha20-Poly1305",
        "token": "chacha20poly1305",
        "kdf": "HKDF-SHA256",
        "aliases": (
            "ChaCha20-Poly1305",
            "chacha20poly1305",
            "chacha20-poly1305",
            "chacha20",
            "chacha",
            "ChaCha20Poly1305",
        ),
    },
    "ascon128": {
        "display_name": "Ascon-AEAD128",
        "token": "ascon128",
        "kdf": "HKDF-SHA256",
        "aliases": (
            "Ascon-AEAD128",
            "Ascon128",
            "asconaead128",
            "ascon-aead128",
            "ascon-aead-128",
            "ascon128",
            "ascon-128",
        ),
    },
    "aegis256": {
        "display_name": "AEGIS-256",
        "token": "aegis256",
        "kdf": "HKDF-SHA256",
        "aliases": (
            "AEGIS-256",
            "aegis256",
            "aegis-256",
            "AEGIS256",
        ),
    },
}

_AEAD_METADATA: Dict[str, Dict[str, object]] = {
    "aesgcm128": {
        "standard_status": "nist_backed",
        "source_standard": "NIST SP 800-38D",
        "security_category": "128-bit key",
        "scheduler_band": "L1",
        "operational_class": "runtime_allowed",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "aesgcm192": {
        "standard_status": "nist_backed",
        "source_standard": "NIST SP 800-38D",
        "security_category": "192-bit key",
        "scheduler_band": "L3",
        "operational_class": "runtime_allowed",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "aesgcm256": {
        "standard_status": "nist_backed",
        "source_standard": "NIST SP 800-38D",
        "security_category": "256-bit key",
        "scheduler_band": "L5",
        "operational_class": "runtime_allowed",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "aesccm128": {
        "standard_status": "nist_backed",
        "source_standard": "NIST SP 800-38C",
        "security_category": "128-bit key",
        "scheduler_band": "L1",
        "operational_class": "runtime_allowed",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "aesccm192": {
        "standard_status": "nist_backed",
        "source_standard": "NIST SP 800-38C",
        "security_category": "192-bit key",
        "scheduler_band": "L3",
        "operational_class": "runtime_allowed",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "aesccm256": {
        "standard_status": "nist_backed",
        "source_standard": "NIST SP 800-38C",
        "security_category": "256-bit key",
        "scheduler_band": "L5",
        "operational_class": "runtime_allowed",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "chacha20poly1305": {
        "standard_status": "ietf_standard",
        "source_standard": "RFC 8439",
        "security_category": "256-bit key",
        "scheduler_band": "L5",
        "operational_class": "runtime_allowed",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "ascon128": {
        "standard_status": "nist_backed",
        "source_standard": "NIST SP 800-232",
        "security_category": "128-bit key",
        "scheduler_band": "L1",
        "operational_class": "runtime_allowed",
        "runtime_allowed": True,
        "benchmark_allowed": True,
    },
    "aegis256": {
        "standard_status": "research_comparator",
        "source_standard": "libsodium AEGIS-256 comparator",
        "security_category": "256-bit key",
        "scheduler_band": "L5",
        "operational_class": "benchmark_only",
        "runtime_allowed": False,
        "benchmark_allowed": True,
    },
}


def _apply_registry_metadata(
    registry: Mapping[str, Mapping[str, object]],
    metadata: Mapping[str, Mapping[str, object]],
) -> Dict[str, Dict[str, object]]:
    enriched: Dict[str, Dict[str, object]] = {}
    for key, entry in registry.items():
        combined = dict(entry)
        extra = dict(metadata.get(key, {}))
        combined.update(extra)
        combined.setdefault("scheduler_band", combined.get("nist_level", "all"))
        combined.setdefault("operational_class", "benchmark_only")
        combined.setdefault("runtime_allowed", False)
        combined.setdefault("benchmark_allowed", True)
        combined.setdefault("standard_status", "unknown")
        combined.setdefault("source_standard", "")
        combined.setdefault("security_category", combined.get("nist_level", ""))
        enriched[key] = combined
    return enriched


_KEM_REGISTRY = _apply_registry_metadata(_KEM_REGISTRY_BASE, _KEM_METADATA)
_SIG_REGISTRY = _apply_registry_metadata(_SIG_REGISTRY_BASE, _SIG_METADATA)
_AEAD_REGISTRY = _apply_registry_metadata(_AEAD_REGISTRY_BASE, _AEAD_METADATA)

_DEFAULT_AEAD_BY_LEVEL: Dict[str, str] = {
    "L1": "aesgcm128",
    "L3": "aesgcm192",
    "L5": "aesgcm256",
}


def _compat_approval_status(*, scheduler_allowed: bool) -> str:
    """Return a simple approved/benchmark-only label for compatibility callers."""

    return "approved" if scheduler_allowed else "benchmark_only"


def _probe_aead_support() -> Tuple[Tuple[str, ...], Dict[str, str]]:
    """Detect AEAD algorithm support available in the current runtime.

    Returns (available_tokens, missing_reason_map).
    """

    available: list[str] = ["aesgcm128", "aesgcm192", "aesgcm256"]
    missing: Dict[str, str] = {}

    # AES-256-CCM (same OpenSSL backend family as AES-GCM, but probe explicitly)
    try:  # pragma: no cover - build dependent
        from cryptography.hazmat.primitives.ciphers.aead import AESCCM  # type: ignore
        if AESCCM is None:  # type: ignore[truthy-bool]
            raise ImportError("AESCCM unavailable in cryptography")
    except Exception as exc:  # pragma: no cover
        missing["aesccm128"] = str(exc)
        missing["aesccm192"] = str(exc)
        missing["aesccm256"] = str(exc)
    else:
        available.extend(("aesccm128", "aesccm192", "aesccm256"))

    # ChaCha20-Poly1305 is optional
    try:  # pragma: no cover - build dependent
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305  # type: ignore
        if ChaCha20Poly1305 is None:  # type: ignore[truthy-bool]
            raise ImportError("ChaCha20Poly1305 unavailable in cryptography")
    except Exception as exc:  # pragma: no cover
        missing["chacha20poly1305"] = str(exc)
    else:
        available.append("chacha20poly1305")

    # AEGIS-256 requires pysodium/libsodium support.
    try:  # pragma: no cover - build/runtime dependent
        import pysodium as _pysodium  # type: ignore
    except Exception as exc:  # pragma: no cover
        missing["aegis256"] = str(exc)
    else:
        if hasattr(_pysodium, "crypto_aead_aegis256_encrypt") and hasattr(_pysodium, "crypto_aead_aegis256_decrypt"):
            available.append("aegis256")
        else:  # pragma: no cover - binding dependent
            missing["aegis256"] = "pysodium missing AEGIS-256 bindings"

    ascon_reason: str | None = None
    ascon_has_standard = False

    try:  # pragma: no cover - build/runtime dependent
        from core import ascon_backend as _ascon  # type: ignore
    except Exception as exc:  # pragma: no cover
        ascon_reason = f"core.ascon_backend unavailable: {exc}"
    else:
        if not hasattr(_ascon, "encrypt") or not hasattr(_ascon, "decrypt"):
            ascon_reason = "core.ascon_backend missing encrypt/decrypt exports"
        else:
            if hasattr(_ascon, "refresh"):
                try:
                    _ascon.refresh()
                except Exception:
                    pass
            has_variant = getattr(_ascon, "has_variant", None)
            missing_reason = getattr(_ascon, "missing_reason", None)
            if callable(has_variant):
                ascon_has_standard = bool(has_variant("Ascon-AEAD128"))
            else:  # pragma: no cover - compatibility path
                ascon_has_standard = True

            if callable(missing_reason):
                ascon_reason = str(missing_reason("Ascon-AEAD128") or "")
            else:  # pragma: no cover - compatibility path
                ascon_reason = "Ascon-AEAD128 unavailable"

    if not bool(_CONFIG.get("ENABLE_ASCON", True)):
        missing["ascon128"] = "disabled_by_config"
    elif ascon_has_standard:
        available.append("ascon128")
    else:
        missing["ascon128"] = ascon_reason or "Ascon-AEAD128 backend unavailable"

    return tuple(available), missing


def available_aead_tokens() -> Tuple[str, ...]:
    """Return the AEAD tokens supported by this runtime."""

    supported, _ = _probe_aead_support()
    return supported


def unavailable_aead_reasons() -> Dict[str, str]:
    """Return descriptive reasons for AEAD algorithms that are unavailable."""

    _, missing = _probe_aead_support()
    return dict(missing)


def list_runtime_suites() -> Dict[str, Dict]:
    """Return scheduler-eligible runtime suites."""

    return {
        suite_id: dict(config)
        for suite_id, config in SUITES.items()
        if bool(config.get("runtime_allowed", False))
    }


def list_benchmark_suites() -> Dict[str, Dict]:
    """Return benchmark-eligible suites, including runtime defaults."""

    return {
        suite_id: dict(config)
        for suite_id, config in SUITES.items()
        if bool(config.get("benchmark_allowed", True))
    }


def runtime_suite_ids() -> Tuple[str, ...]:
    """Return canonical runtime suite IDs in deterministic order."""

    return tuple(sorted(list_runtime_suites().keys()))


def benchmark_suite_ids() -> Tuple[str, ...]:
    """Return canonical benchmark suite IDs in deterministic order."""

    return tuple(sorted(list_benchmark_suites().keys()))


def runtime_aead_tokens(*, require_available: bool = True) -> Tuple[str, ...]:
    """Return AEAD tokens the runtime scheduler may auto-select."""

    available = set(available_aead_tokens()) if require_available else None
    tokens: list[str] = []
    for entry in _AEAD_REGISTRY.values():
        token = str(entry.get("token", ""))
        if not token or not bool(entry.get("runtime_allowed", False)):
            continue
        if available is not None and token not in available:
            continue
        tokens.append(token)
    return tuple(dict.fromkeys(tokens))


def benchmark_aead_tokens(*, require_available: bool = False) -> Tuple[str, ...]:
    """Return AEAD tokens allowed for benchmark and research paths."""

    available = set(available_aead_tokens()) if require_available else None
    tokens: list[str] = []
    for entry in _AEAD_REGISTRY.values():
        token = str(entry.get("token", ""))
        if not token or not bool(entry.get("benchmark_allowed", True)):
            continue
        if available is not None and token not in available:
            continue
        tokens.append(token)
    return tuple(dict.fromkeys(tokens))


def is_runtime_suite_allowed(suite_id: str) -> bool:
    """Return True if the suite is operationally eligible for runtime policy."""

    try:
        suite = get_suite(suite_id)
    except Exception:
        return False
    return bool(suite.get("runtime_allowed", False))


def is_runtime_aead_allowed(token: str) -> bool:
    """Return True if the AEAD token is operationally eligible for runtime policy."""

    try:
        normalized = normalize_aead_token(token)
    except ValueError:
        return False
    entry = _AEAD_REGISTRY.get(normalized)
    return bool(entry and entry.get("runtime_allowed", False))


def _build_alias_map(registry: Dict[str, Dict]) -> Dict[str, str]:
    alias_map: Dict[str, str] = {}
    for key, entry in registry.items():
        for alias in entry["aliases"]:
            normalized = _normalize_alias(alias)
            alias_map[normalized] = key
        alias_map[_normalize_alias(entry["oqs_name"]) if "oqs_name" in entry else _normalize_alias(entry["display_name"])] = key
        alias_map[_normalize_alias(entry["token"])] = key
    return alias_map


_KEM_ALIASES = _build_alias_map(_KEM_REGISTRY)
_SIG_ALIASES = _build_alias_map(_SIG_REGISTRY)
_AEAD_ALIASES = _build_alias_map(_AEAD_REGISTRY)


def _resolve_kem_key(name: str) -> str:
    lookup = _KEM_ALIASES.get(_normalize_alias(name))
    if lookup is None:
        raise ValueError(f"unknown KEM: {name}")
    return lookup


def _resolve_sig_key(name: str) -> str:
    lookup = _SIG_ALIASES.get(_normalize_alias(name))
    if lookup is None:
        raise ValueError(f"unknown signature: {name}")
    return lookup


def _resolve_aead_key(name: str) -> str:
    lookup = _AEAD_ALIASES.get(_normalize_alias(name))
    if lookup is None:
        raise ValueError(f"unknown AEAD: {name}")
    return lookup


def normalize_aead_token(name: str) -> str:
    """Return canonical AEAD token from an alias/name."""

    aead_key = _resolve_aead_key(name)
    entry = _AEAD_REGISTRY.get(aead_key)
    if not entry:
        raise ValueError(f"unknown AEAD: {name}")
    return str(entry["token"])


_GENERIC_AEAD_LEVEL_MAP: Dict[str, Dict[str, str]] = {
    "aesgcm": {
        "L1": "aesgcm128",
        "L3": "aesgcm192",
        "L5": "aesgcm256",
    },
    "aesccm": {
        "L1": "aesccm128",
        "L3": "aesccm192",
        "L5": "aesccm256",
    },
    "ascon": {
        "L1": "ascon128",
        "L3": "ascon128",
        "L5": "ascon128",
    },
    "chacha20poly1305": {
        "L1": "chacha20poly1305",
        "L3": "chacha20poly1305",
        "L5": "chacha20poly1305",
    },
}
_GENERIC_AEAD_ALIASES: Dict[str, str] = {
    "aesgcm": "aesgcm",
    "aes-gcm": "aesgcm",
    "aesccm": "aesccm",
    "aes-ccm": "aesccm",
    "ascon": "ascon",
    "ascon128": "ascon",
    "ascon-128": "ascon",
    "chacha20poly1305": "chacha20poly1305",
    "chacha20-poly1305": "chacha20poly1305",
}


def normalize_aead_token_for_level(name: str, nist_level: str) -> str:
    """Resolve an AEAD name into a concrete profile token for the given level."""

    level = str(nist_level or "").strip().upper()
    alias = _normalize_alias(name)
    family = _GENERIC_AEAD_ALIASES.get(alias)
    if family:
        level_map = _GENERIC_AEAD_LEVEL_MAP.get(family, {})
        resolved = level_map.get(level)
        if not resolved:
            raise ValueError(f"AEAD family {family} is not defined for level {level}")
        return resolved
    normalized = normalize_aead_token(name)
    allowed = set(_AEAD_PROFILES_BY_LEVEL.get(level, ()))
    if allowed and normalized not in allowed:
        raise ValueError(f"AEAD {normalized} is not valid for level {level}")
    return normalized


def build_suite_id(kem: str, sig: str) -> str:
    """Build canonical KEM+SIG suite identifier.  AEAD is runtime config (TLS 1.3 model)."""

    kem_key = _resolve_kem_key(kem)
    sig_key = _resolve_sig_key(sig)

    kem_entry = _KEM_REGISTRY[kem_key]
    sig_entry = _SIG_REGISTRY[sig_key]

    return f"cs-{kem_entry['token']}-{sig_entry['token']}"


_SUITE_ALIASES: Dict[str, str] = {}


def _compose_suite(kem_key: str, sig_key: str) -> Dict[str, object]:
    """Compose a suite dict for a KEM+SIG pair.  AEAD is runtime config (TLS 1.3 model)."""
    kem_entry = _KEM_REGISTRY[kem_key]
    sig_entry = _SIG_REGISTRY[sig_key]
    level = str(kem_entry["nist_level"])
    default_aead_token = _DEFAULT_AEAD_BY_LEVEL.get(level, "aesgcm256")
    aead_entry = _AEAD_REGISTRY[default_aead_token]

    if kem_entry["nist_level"] != sig_entry["nist_level"]:
        raise NotImplementedError(
            f"NIST level mismatch for {kem_entry['oqs_name']} / {sig_entry['oqs_name']}"
        )

    suite_id = f"cs-{kem_entry['token']}-{sig_entry['token']}"
    key_handshake_id = f"khs-{kem_entry['token']}-{sig_entry['token']}"
    data_aead_id = f"dap-{aead_entry['token']}"
    is_runtime_default = suite_id in OPERATIONAL_DEFAULT_SUITE_IDS
    kem_status = str(kem_entry.get("standard_status", "unknown"))
    sig_status = str(sig_entry.get("standard_status", "unknown"))
    if is_runtime_default:
        profile_status = "approved_operational"
        operational_class = "runtime_default"
    elif kem_status == "approved" and sig_status == "approved":
        profile_status = "approved_benchmark_only"
        operational_class = "benchmark_only"
    elif kem_status in {"selected_future", "future_track"} or sig_status in {"selected_future", "future_track"}:
        profile_status = "future_track_benchmark"
        operational_class = "benchmark_only"
    else:
        profile_status = "experimental_benchmark"
        operational_class = "benchmark_only"
    scheduler_allowed = is_runtime_default
    aead_scheduler_allowed = bool(aead_entry.get("runtime_allowed", False))

    return {
        "suite_id": suite_id,
        "key_handshake_id": key_handshake_id,
        "key_handshake": f"{kem_entry['oqs_name']}+{sig_entry['oqs_name']}",
        "data_aead_id": data_aead_id,
        "data_aead": aead_entry["display_name"],
        "negotiation_scope": "key_handshake=kem+sig,data_plane=aead",
        "kem_name": kem_entry["oqs_name"],
        "kem_id": kem_entry["kem_id"],
        "kem_param_id": kem_entry["kem_param_id"],
        "sig_name": sig_entry["oqs_name"],
        "sig_id": sig_entry["sig_id"],
        "sig_param_id": sig_entry["sig_param_id"],
        "nist_level": kem_entry["nist_level"],
        "scheduler_band": kem_entry["nist_level"],
        "security_category": (
            f"kem={kem_entry.get('security_category', kem_entry['nist_level'])};"
            f"sig={sig_entry.get('security_category', sig_entry['nist_level'])}"
        ),
        "standard_status": profile_status,
        "source_standard": f"{kem_entry.get('source_standard', '')} + {sig_entry.get('source_standard', '')}".strip(" +"),
        "operational_class": operational_class,
        "runtime_allowed": is_runtime_default,
        "benchmark_allowed": True,
        "operational_default": is_runtime_default,
        "approval_status": _compat_approval_status(scheduler_allowed=scheduler_allowed),
        "scheduler_allowed": scheduler_allowed,
        "kem_token": kem_entry["token"],
        "sig_token": sig_entry["token"],
        "kem_standard_status": kem_status,
        "sig_standard_status": sig_status,
        "kem_source_standard": kem_entry.get("source_standard", ""),
        "sig_source_standard": sig_entry.get("source_standard", ""),
        "kem_security_category": kem_entry.get("security_category", kem_entry["nist_level"]),
        "sig_security_category": sig_entry.get("security_category", sig_entry["nist_level"]),
        "aead": aead_entry["display_name"],
        "kdf": aead_entry["kdf"],
        "aead_token": aead_entry["token"],
        "kem_approval_status": _compat_approval_status(
            scheduler_allowed=bool(kem_entry.get("runtime_allowed", False))
        ),
        "sig_approval_status": _compat_approval_status(
            scheduler_allowed=bool(sig_entry.get("runtime_allowed", False))
        ),
        "aead_approval_status": _compat_approval_status(
            scheduler_allowed=aead_scheduler_allowed
        ),
    }

def _generate_level_consistent_matrix() -> Tuple[Tuple[str, str], ...]:
    """Generate matrix of (kem_key, sig_key) pairs sharing identical NIST level.

    This expands prior static matrix to all level-aligned combinations while
    preserving backward compatibility (legacy combos remain valid subset).
    """
    # Allow runtime ignore list for KEMs: keep registry entries,
    # but avoid generating suites that include ignored primitives.
    _DEFAULT_IGNORED_KEMS = ()

    # Environment overrides (comma-separated keys matching registry keys)
    ignored_kems_env = os.getenv("SUITES_IGNORE_KEMS", "").strip()

    ignored_kems = set(_DEFAULT_IGNORED_KEMS)
    if ignored_kems_env:
        ignored_kems.update(k.strip() for k in ignored_kems_env.split(",") if k.strip())

    pairs: list[Tuple[str, str]] = []
    for kem_key, kem_entry in _KEM_REGISTRY.items():
        if kem_key in ignored_kems:
            # skip composing suites with ignored KEMs
            continue
        kem_level = kem_entry.get("nist_level")
        for sig_key, sig_entry in _SIG_REGISTRY.items():
            if sig_entry.get("nist_level") == kem_level:
                pairs.append((kem_key, sig_key))
    # Deterministic order: sort by kem token then signature token
    pairs.sort(key=lambda t: (t[0], t[1]))
    return tuple(pairs)

_SUITE_MATRIX: Tuple[Tuple[str, str], ...] = _generate_level_consistent_matrix()

_AEAD_ORDER: Tuple[str, ...] = (
    "aesgcm128",
    "aesccm128",
    "ascon128",
    "aesgcm192",
    "aesccm192",
    "aesgcm256",
    "aesccm256",
    "chacha20poly1305",
    "aegis256",
)

# AEAD profile matrix requested for key-handshake NIST levels.
# Total profiles: 3 (L1) + 2 (L3) + 3 (L5) = 8.
_AEAD_PROFILES_BY_LEVEL: Dict[str, Tuple[str, ...]] = {
    "L1": ("aesgcm128", "aesccm128", "ascon128"),
    "L3": ("aesgcm192", "aesccm192"),
    "L5": ("aesgcm256", "aesccm256", "chacha20poly1305"),
}


def aead_profiles_by_nist_level(*, runtime_only: bool = False) -> Dict[str, Tuple[str, ...]]:
    """Return level-aware AEAD profile matrix.

    If runtime_only=True, only include tokens available in this runtime.
    """

    if not runtime_only:
        return {level: tuple(tokens) for level, tokens in _AEAD_PROFILES_BY_LEVEL.items()}

    runtime_tokens = set(available_aead_tokens())
    filtered: Dict[str, Tuple[str, ...]] = {}
    for level, tokens in _AEAD_PROFILES_BY_LEVEL.items():
        filtered[level] = tuple(token for token in tokens if token in runtime_tokens)
    return filtered


def approved_aead_profiles_by_nist_level(*, runtime_only: bool = False) -> Dict[str, Tuple[str, ...]]:
    """Return the runtime-approved AEAD matrix by NIST level."""

    matrix = aead_profiles_by_nist_level(runtime_only=runtime_only)
    approved_tokens = {
        str(entry.get("token", ""))
        for entry in _AEAD_REGISTRY.values()
        if bool(entry.get("runtime_allowed", False))
    }
    filtered: Dict[str, Tuple[str, ...]] = {}
    for level, tokens in matrix.items():
        filtered[level] = tuple(token for token in tokens if token in approved_tokens)
    return filtered

def valid_nist_levels() -> Tuple[str, ...]:
    """Return distinct NIST security levels present in the registry."""
    levels = {entry["nist_level"] for entry in _KEM_REGISTRY.values()} | {entry["nist_level"] for entry in _SIG_REGISTRY.values()}
    ordered = sorted(levels)
    return tuple(ordered)

def list_suites_for_level(level: str) -> Dict[str, Dict]:
    """List suites restricted to a single NIST level.

    Raises ValueError if level is not present. Returns mapping of suite_id->suite dict copy.
    """
    if level not in {e["nist_level"] for e in _KEM_REGISTRY.values()}:
        raise ValueError(f"unknown NIST level: {level}")
    result: Dict[str, Dict] = {}
    for sid, cfg in SUITES.items():
        if cfg.get("nist_level") == level:
            result[sid] = dict(cfg)
    return result

def filter_suites_by_levels(levels: Iterable[str]) -> Tuple[str, ...]:
    """Return tuple of suite_ids whose nist_level is in provided iterable.

    Invalid levels raise ValueError.
    """
    level_set = set(levels)
    known = {e["nist_level"] for e in _KEM_REGISTRY.values()}
    if not level_set.issubset(known):
        unknown = level_set - known
        raise ValueError(f"unknown NIST levels requested: {sorted(unknown)}")
    return tuple(sid for sid, cfg in SUITES.items() if cfg.get("nist_level") in level_set)


def _canonicalize_suite_id(suite_id: str) -> str:
    if not suite_id:
        raise ValueError("suite_id cannot be empty")

    candidate = suite_id.strip()
    if candidate in _SUITE_ALIASES:
        return _SUITE_ALIASES[candidate]

    if not candidate.startswith("cs-"):
        raise NotImplementedError(f"unknown suite_id: {suite_id}")

    parts = candidate[3:].split("-")
    # New format: cs-{kem}-{sig}  (2 parts)
    if len(parts) == 2:
        kem_part, sig_part = parts
        try:
            return build_suite_id(kem_part, sig_part)
        except ValueError as exc:
            raise ValueError(f"unknown suite_id: {suite_id}") from exc
    raise NotImplementedError(f"unknown suite_id: {suite_id}")


def _generate_suite_registry() -> MappingProxyType:
    """Generate 24 KEM+SIG suites.  AEAD is separate runtime config (TLS 1.3 model)."""
    suites: Dict[str, MappingProxyType] = {}
    for kem_key, sig_key in _SUITE_MATRIX:
        if kem_key not in _KEM_REGISTRY:
            raise ValueError(f"unknown KEM in suite matrix: {kem_key}")
        if sig_key not in _SIG_REGISTRY:
            raise ValueError(f"unknown signature in suite matrix: {sig_key}")
        suite_dict = _compose_suite(kem_key, sig_key)
        suites[suite_dict["suite_id"]] = MappingProxyType(suite_dict)
    return MappingProxyType(suites)


SUITES = _generate_suite_registry()


def list_suites() -> Dict[str, Dict]:
    """Return all available suites as immutable mapping."""

    return {suite_id: dict(config) for suite_id, config in SUITES.items()}


def list_scheduler_approved_suites() -> Dict[str, Dict]:
    """Return the scheduler-approved operational suite subset."""

    return {
        suite_id: dict(config)
        for suite_id, config in SUITES.items()
        if bool(config.get("scheduler_allowed", config.get("runtime_allowed", False)))
    }


def get_suite(suite_id: str) -> Dict:
    """Get suite configuration by ID, resolving legacy aliases and synonyms."""

    canonical_id = _canonicalize_suite_id(suite_id)

    if canonical_id not in SUITES:
        raise NotImplementedError(f"unknown suite_id: {suite_id}")

    suite = SUITES[canonical_id]

    required_fields = {"kem_name", "sig_name", "aead", "kdf", "nist_level"}
    missing_fields = required_fields - set(suite.keys())
    if missing_fields:
        raise ValueError(f"malformed suite {suite_id}: missing fields {missing_fields}")

    return dict(suite)


def negotiation_profiles_for_suite(suite: Dict) -> Dict[str, str]:
    """Return split negotiation profile IDs for a suite-like object."""

    if not isinstance(suite, dict):
        raise ValueError("suite must be a dictionary")

    suite_id = suite.get("suite_id")
    if isinstance(suite_id, str) and suite_id.strip():
        resolved = get_suite(suite_id)
    else:
        try:
            canonical = build_suite_id(suite["kem_name"], suite["sig_name"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("suite must include suite_id or canonical kem/sig fields") from exc
        resolved = get_suite(canonical)

    return {
        "suite_id": str(resolved["suite_id"]),
        "key_handshake_id": str(resolved["key_handshake_id"]),
        "key_handshake": str(resolved["key_handshake"]),
        "data_aead_id": str(resolved["data_aead_id"]),
        "data_aead": str(resolved["data_aead"]),
        "negotiation_scope": str(resolved["negotiation_scope"]),
    }


def _normalize_token_list(
    values: Optional[Iterable[str]],
    resolver,
) -> Optional[Tuple[str, ...]]:
    if values is None:
        return None
    out: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        token = value.strip()
        if not token:
            continue
        try:
            out.append(resolver(token))
        except ValueError:
            continue
    return tuple(dict.fromkeys(out))


def _preference_rank(value: str, preference: Optional[Tuple[str, ...]]) -> int:
    if not preference:
        return 0
    try:
        return preference.index(value)
    except ValueError:
        return len(preference) + 100


def _normalize_selection_scope(selection_scope: str) -> str:
    scope = str(selection_scope or "runtime").strip().lower()
    if scope not in {"runtime", "benchmark", "all"}:
        raise ValueError(f"unknown selection scope: {selection_scope}")
    return scope


def _suite_allowed_in_scope(suite: Mapping[str, object], selection_scope: str) -> bool:
    scope = _normalize_selection_scope(selection_scope)
    if scope == "all":
        return True
    flag_name = "runtime_allowed" if scope == "runtime" else "benchmark_allowed"
    return bool(suite.get(flag_name, False if scope == "runtime" else True))


def _aead_allowed_in_scope(token: str, selection_scope: str) -> bool:
    scope = _normalize_selection_scope(selection_scope)
    if scope == "all":
        return True
    entry = _AEAD_REGISTRY.get(token)
    if not entry:
        return False
    flag_name = "runtime_allowed" if scope == "runtime" else "benchmark_allowed"
    return bool(entry.get(flag_name, False if scope == "runtime" else True))


def _select_suite_id_for_capabilities(
    *,
    offered_suites: Optional[Iterable[str]] = None,
    kem_tokens: Optional[Iterable[str]] = None,
    sig_tokens: Optional[Iterable[str]] = None,
    prefer_kem_tokens: Optional[Iterable[str]] = None,
    prefer_sig_tokens: Optional[Iterable[str]] = None,
    selection_scope: str = "runtime",
    scheduler_only: bool = False,
) -> str:
    """Select canonical suite ID from KEM/SIG capability offers/preferences.

    Raises NotImplementedError when no candidate suite matches constraints.
    """

    allowed_kems = _normalize_token_list(kem_tokens, _resolve_kem_key)
    allowed_sigs = _normalize_token_list(sig_tokens, _resolve_sig_key)

    prefer_kems = _normalize_token_list(prefer_kem_tokens, _resolve_kem_key)
    prefer_sigs = _normalize_token_list(prefer_sig_tokens, _resolve_sig_key)

    candidate_ids: list[str] = []
    if offered_suites is not None:
        for offered in offered_suites:
            if not isinstance(offered, str):
                continue
            try:
                canonical = _canonicalize_suite_id(offered)
            except (ValueError, NotImplementedError):
                continue
            if canonical in SUITES:
                candidate_ids.append(canonical)
        candidate_ids = list(dict.fromkeys(candidate_ids))
    else:
        candidate_ids = list(SUITES.keys())

    resolved_scope = "runtime" if scheduler_only else selection_scope
    candidate_ids = [
        suite_id for suite_id in candidate_ids
        if _suite_allowed_in_scope(SUITES.get(suite_id, {}), resolved_scope)
    ]

    # If the caller provided no explicit capability offers or preferences,
    # prefer the configured default suite when it satisfies the constraints.
    # This avoids unintentionally selecting the lexicographically-first runtime
    # suite (often the lowest NIST level) purely due to deterministic ordering.
    if (
        offered_suites is None
        and not prefer_kems
        and not prefer_sigs
        and DEFAULT_SUITE_ID in candidate_ids
    ):
        default_suite = SUITES.get(DEFAULT_SUITE_ID)
        if default_suite is not None:
            try:
                default_kem_key = _resolve_kem_key(str(default_suite["kem_name"]))
                default_sig_key = _resolve_sig_key(str(default_suite["sig_name"]))
            except Exception:
                default_kem_key = None
                default_sig_key = None
            default_scheduler_ok = (
                (not scheduler_only)
                or bool(default_suite.get("scheduler_allowed", default_suite.get("runtime_allowed", False)))
            )
            default_allowed_ok = (
                (allowed_kems is None or (default_kem_key in allowed_kems))
                and (allowed_sigs is None or (default_sig_key in allowed_sigs))
            )
            if default_scheduler_ok and default_allowed_ok:
                return DEFAULT_SUITE_ID

    best_suite_id: Optional[str] = None
    best_key: Optional[Tuple[int, int, str]] = None
    for suite_id in candidate_ids:
        suite = SUITES.get(suite_id)
        if suite is None:
            continue

        try:
            kem_key = _resolve_kem_key(str(suite["kem_name"]))
            sig_key = _resolve_sig_key(str(suite["sig_name"]))
        except (KeyError, TypeError, ValueError):
            continue

        if scheduler_only and not bool(suite.get("scheduler_allowed", suite.get("runtime_allowed", False))):
            continue

        if allowed_kems is not None and kem_key not in allowed_kems:
            continue
        if allowed_sigs is not None and sig_key not in allowed_sigs:
            continue

        sort_key = (
            _preference_rank(kem_key, prefer_kems),
            _preference_rank(sig_key, prefer_sigs),
            suite_id,
        )
        if best_key is None or sort_key < best_key:
            best_key = sort_key
            best_suite_id = suite_id

    if best_suite_id is None:
        raise NotImplementedError("no suite matches offered capabilities")
    return best_suite_id


def _select_aead_token_for_capabilities(
    *,
    nist_level: Optional[str] = None,
    aead_tokens: Optional[Iterable[str]] = None,
    prefer_aead_tokens: Optional[Iterable[str]] = None,
    selection_scope: str = "runtime",
    scheduler_only: bool = False,
) -> str:
    """Select canonical AEAD token from runtime availability and preferences."""

    def _normalize_aead_list(values: Optional[Iterable[str]]) -> Optional[Tuple[str, ...]]:
        if values is None:
            return None
        out: list[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            token = value.strip()
            if not token:
                continue
            try:
                if nist_level is not None:
                    out.append(normalize_aead_token_for_level(token, str(nist_level)))
                else:
                    out.append(normalize_aead_token(token))
            except ValueError:
                continue
        return tuple(dict.fromkeys(out))

    allowed_aeads = _normalize_aead_list(aead_tokens)
    prefer_aeads = _normalize_aead_list(prefer_aead_tokens)

    resolved_scope = "runtime" if scheduler_only else selection_scope
    runtime_aead_keys: list[str] = []
    for runtime_token in available_aead_tokens():
        try:
            resolved = _resolve_aead_key(runtime_token)
        except ValueError:
            continue
        if _aead_allowed_in_scope(resolved, resolved_scope):
            runtime_aead_keys.append(resolved)
    runtime_aead_keys = list(dict.fromkeys(runtime_aead_keys))

    if nist_level is not None:
        level = str(nist_level).strip().upper()
        allowed_by_level = _AEAD_PROFILES_BY_LEVEL.get(level)
        if not allowed_by_level:
            raise NotImplementedError(f"no AEAD profile defined for nist level: {nist_level}")
        level_keys: list[str] = []
        for token in allowed_by_level:
            try:
                level_keys.append(_resolve_aead_key(token))
            except ValueError:
                continue
        runtime_aead_keys = [token for token in runtime_aead_keys if token in set(level_keys)]

    if not runtime_aead_keys:
        raise NotImplementedError("no AEAD available in runtime for selected profile constraints")

    candidate_aeads = [
        token for token in runtime_aead_keys
        if allowed_aeads is None or token in allowed_aeads
    ]
    if not candidate_aeads:
        raise NotImplementedError("no AEAD matches offered capabilities")

    aead_order_index = {token: idx for idx, token in enumerate(_AEAD_ORDER)}
    selected_aead_key = min(
        candidate_aeads,
        key=lambda token: (
            _preference_rank(token, prefer_aeads),
            aead_order_index.get(token, len(aead_order_index) + 100),
            token,
        ),
    )
    entry = _AEAD_REGISTRY.get(selected_aead_key)
    if not entry:
        raise NotImplementedError("selected AEAD missing from registry")
    return str(entry["token"])


def select_crypto_profile_for_capabilities(
    *,
    offered_suites: Optional[Iterable[str]] = None,
    kem_tokens: Optional[Iterable[str]] = None,
    sig_tokens: Optional[Iterable[str]] = None,
    aead_tokens: Optional[Iterable[str]] = None,
    prefer_kem_tokens: Optional[Iterable[str]] = None,
    prefer_sig_tokens: Optional[Iterable[str]] = None,
    prefer_aead_tokens: Optional[Iterable[str]] = None,
    selection_scope: str = "runtime",
    scheduler_only: bool = False,
) -> Dict[str, str]:
    """Select a split crypto profile: key-handshake suite + AEAD token."""

    suite_id = _select_suite_id_for_capabilities(
        offered_suites=offered_suites,
        kem_tokens=kem_tokens,
        sig_tokens=sig_tokens,
        prefer_kem_tokens=prefer_kem_tokens,
        prefer_sig_tokens=prefer_sig_tokens,
        selection_scope=selection_scope,
        scheduler_only=scheduler_only,
    )
    suite = SUITES.get(suite_id)
    if suite is None:
        raise NotImplementedError("selected suite not present in registry")

    aead_token = _select_aead_token_for_capabilities(
        nist_level=str(suite.get("nist_level", "")),
        aead_tokens=aead_tokens,
        prefer_aead_tokens=prefer_aead_tokens,
        selection_scope=selection_scope,
        scheduler_only=scheduler_only,
    )
    nist_level = str(suite.get("nist_level", ""))
    aead_key = _resolve_aead_key(aead_token)
    aead_entry = _AEAD_REGISTRY.get(aead_key, {})
    suite_scheduler_allowed = bool(suite.get("scheduler_allowed", suite.get("runtime_allowed", False)))
    profile_scheduler_allowed = suite_scheduler_allowed and bool(aead_entry.get("runtime_allowed", False))
    return {
        "suite_id": suite_id,
        "key_handshake_id": str(suite.get("key_handshake_id", "")),
        "aead_token": aead_token,
        "data_aead_id": f"dap-{aead_token}",
        "nist_level": nist_level,
        "aead_profile_id": f"aead-{nist_level.lower()}-{aead_token}" if nist_level else f"aead-{aead_token}",
        "suite_approval_status": str(
            suite.get(
                "approval_status",
                _compat_approval_status(scheduler_allowed=suite_scheduler_allowed),
            )
        ),
        "aead_approval_status": _compat_approval_status(
            scheduler_allowed=bool(aead_entry.get("runtime_allowed", False))
        ),
        "approval_status": _compat_approval_status(scheduler_allowed=profile_scheduler_allowed),
        "scheduler_allowed": profile_scheduler_allowed,
        "standard_status": str(suite.get("standard_status", "")),
        "operational_class": str(suite.get("operational_class", "")),
        "security_category": str(suite.get("security_category", "")),
    }


def select_suite_id_for_capabilities(
    *,
    offered_suites: Optional[Iterable[str]] = None,
    kem_tokens: Optional[Iterable[str]] = None,
    sig_tokens: Optional[Iterable[str]] = None,
    aead_tokens: Optional[Iterable[str]] = None,
    prefer_kem_tokens: Optional[Iterable[str]] = None,
    prefer_sig_tokens: Optional[Iterable[str]] = None,
    prefer_aead_tokens: Optional[Iterable[str]] = None,
    selection_scope: str = "runtime",
    scheduler_only: bool = False,
) -> str:
    """Compatibility selector returning only suite_id from the full crypto profile."""

    profile = select_crypto_profile_for_capabilities(
        offered_suites=offered_suites,
        kem_tokens=kem_tokens,
        sig_tokens=sig_tokens,
        aead_tokens=aead_tokens,
        prefer_kem_tokens=prefer_kem_tokens,
        prefer_sig_tokens=prefer_sig_tokens,
        prefer_aead_tokens=prefer_aead_tokens,
        selection_scope=selection_scope,
        scheduler_only=scheduler_only,
    )
    return profile["suite_id"]


def _safe_get_enabled_kem_mechanisms() -> Iterable[str]:
    # Try different import styles for oqs-python compatibility
    # Style 1: from oqs.oqs import ...
    try:
        try:
            from oqs.oqs import get_enabled_KEM_mechanisms as kem_loader
        except ImportError:
            from oqs.oqs import get_enabled_kem_mechanisms as kem_loader
        return kem_loader()
    except (ImportError, ModuleNotFoundError):
        pass
    
    # Style 2: from oqs import ...
    try:
        try:
            from oqs import get_enabled_KEM_mechanisms as kem_loader
        except ImportError:
            from oqs import get_enabled_kem_mechanisms as kem_loader
        return kem_loader()
    except (ImportError, ModuleNotFoundError):
        pass
    
    # Style 3: import oqs; oqs.X
    try:
        import oqs
        if hasattr(oqs, 'get_enabled_KEM_mechanisms'):
            return oqs.get_enabled_KEM_mechanisms()
        else:
            return oqs.get_enabled_kem_mechanisms()
    except (ImportError, ModuleNotFoundError, AttributeError):
        pass
    
    return []


def _safe_get_enabled_sig_mechanisms() -> Iterable[str]:
    # Try different import styles for oqs-python compatibility
    # Style 1: from oqs.oqs import ...
    try:
        try:
            from oqs.oqs import get_enabled_sig_mechanisms as sig_loader
        except ImportError:
            from oqs.oqs import get_enabled_SIG_mechanisms as sig_loader
        return sig_loader()
    except (ImportError, ModuleNotFoundError):
        pass
    
    # Style 2: from oqs import ...
    try:
        try:
            from oqs import get_enabled_sig_mechanisms as sig_loader
        except ImportError:
            from oqs import get_enabled_SIG_mechanisms as sig_loader
        return sig_loader()
    except (ImportError, ModuleNotFoundError):
        pass
    
    # Style 3: import oqs; oqs.X
    try:
        import oqs
        if hasattr(oqs, 'get_enabled_sig_mechanisms'):
            return oqs.get_enabled_sig_mechanisms()
        else:
            return oqs.get_enabled_SIG_mechanisms()
    except (ImportError, ModuleNotFoundError, AttributeError):
        pass
    
    return []


def enabled_kems() -> Tuple[str, ...]:
    """Return tuple of oqs KEM mechanism names supported by the runtime."""

    mechanisms = {_normalize_alias(name) for name in _safe_get_enabled_kem_mechanisms()}
    result = [
        entry["oqs_name"]
        for entry in _KEM_REGISTRY.values()
        if _normalize_alias(entry["oqs_name"]) in mechanisms
    ]
    return tuple(result)


def enabled_sigs() -> Tuple[str, ...]:
    """Return tuple of oqs signature mechanism names supported by the runtime."""

    mechanisms = {_normalize_alias(name) for name in _safe_get_enabled_sig_mechanisms()}
    result = [
        entry["oqs_name"]
        for entry in _SIG_REGISTRY.values()
        if _normalize_alias(entry["oqs_name"]) in mechanisms
    ]
    return tuple(result)


def _prune_suites_for_runtime() -> None:
    """Filter suites by runtime KEM/SIG availability, preserving immutability."""

    global SUITES
    available_kems: set[str] = set()
    available_sigs: set[str] = set()
    try:
        available_kems = set(enabled_kems())
    except Exception:
        available_kems = set()
    try:
        available_sigs = set(enabled_sigs())
    except Exception:
        available_sigs = set()

    # If runtime probing failed for both dimensions, preserve static registry.
    if not available_kems and not available_sigs:
        return

    filtered: Dict[str, MappingProxyType] = {}
    removed: list[dict[str, str]] = []
    for suite_id, config in SUITES.items():
        sig_name = str(config.get("sig_name", ""))
        kem_name = str(config.get("kem_name", ""))
        sig_ok = (not available_sigs) or (sig_name in available_sigs)
        kem_ok = (not available_kems) or (kem_name in available_kems)
        if sig_ok and kem_ok:
            filtered[suite_id] = config
        else:
            removed.append(
                {
                    "suite_id": suite_id,
                    "kem_name": kem_name,
                    "sig_name": sig_name,
                    "kem_supported": str(kem_ok).lower(),
                    "sig_supported": str(sig_ok).lower(),
                }
            )

    if not removed:
        return

    _logger.warning(
        "Pruning suites with unsupported runtime KEM/SIG algorithms",
        extra={
            "removed_suites": removed,
            "available_kems": sorted(available_kems),
            "available_sigs": sorted(available_sigs),
        },
    )
    from types import MappingProxyType as _MP

    SUITES = _MP(filtered)  # type: ignore[assignment]


def header_ids_for_suite(suite: Dict) -> Tuple[int, int, int, int]:
    """Return embedded header ID bytes for provided suite dict copy."""

    try:
        return (
            suite["kem_id"],
            suite["kem_param_id"],
            suite["sig_id"],
            suite["sig_param_id"],
        )
    except KeyError as e:
        raise ValueError(f"suite missing embedded id field: {e}")


def header_ids_from_names(kem_name: str, sig_name: str) -> Tuple[int, int, int, int]:
    """Return header IDs from algorithm names.
    
    Used by async_proxy.py for runtime header ID resolution when
    kem_name and sig_name are returned from the handshake.
    """
    kem_key = _resolve_kem_key(kem_name)
    sig_key = _resolve_sig_key(sig_name)
    kem_entry = _KEM_REGISTRY[kem_key]
    sig_entry = _SIG_REGISTRY[sig_key]
    return (
        kem_entry["kem_id"],
        kem_entry["kem_param_id"],
        sig_entry["sig_id"],
        sig_entry["sig_param_id"],
    )


def suite_bytes_for_hkdf(suite: Dict) -> bytes:
    """Generate deterministic bytes from suite for HKDF info parameter."""

    if "suite_id" in suite:
        return suite["suite_id"].encode("utf-8")

    try:
        suite_id = build_suite_id(suite["kem_name"], suite["sig_name"])
    except (KeyError, ValueError) as exc:
        raise ValueError("Suite configuration not found in registry") from exc

    return suite_id.encode("utf-8")


_prune_suites_for_runtime()
