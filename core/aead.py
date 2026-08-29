"""
AEAD framing for PQC drone-GCS secure proxy.

Provides authenticated encryption (AES-256-GCM) with wire header bound as AAD,
deterministic 96-bit counter IVs, sliding replay window, and epoch support for rekeys.
"""

import struct
from dataclasses import dataclass
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.exceptions import InvalidTag

try:  # pragma: no cover - native library wrapper optional
    from core import ascon_backend as _ascon_module
except Exception:  # pragma: no cover - extension not built or unavailable
    _ascon_module = None

try:  # pragma: no cover - AEGIS-256 via libsodium (>= 1.0.19)
    import pysodium as _pysodium_module  # type: ignore
except Exception:  # pragma: no cover
    _pysodium_module = None

from core.config import CONFIG
from core.exceptions import SequenceOverflow, AeadError


_SUPPORTED_AEAD_TOKENS = {
    "aesgcm128",
    "aesgcm192",
    "aesgcm256",
    "aesccm128",
    "aesccm192",
    "aesccm256",
    "chacha20poly1305",
    "ascon128",
}
_AEAD_TOKEN_ALIASES = {
    "aesgcm": "aesgcm256",
    "aes128gcm": "aesgcm128",
    "aes192gcm": "aesgcm192",
    "aes256gcm": "aesgcm256",
    "aes-128-gcm": "aesgcm128",
    "aes-192-gcm": "aesgcm192",
    "aes-256-gcm": "aesgcm256",
    "aesccm": "aesccm256",
    "aes128ccm": "aesccm128",
    "aes192ccm": "aesccm192",
    "aes256ccm": "aesccm256",
    "aes-128-ccm": "aesccm128",
    "aes-192-ccm": "aesccm192",
    "aes-256-ccm": "aesccm256",
    "chacha20": "chacha20poly1305",
    "chacha": "chacha20poly1305",
    "ascon": "ascon128",
}
_RETIRED_AEAD_TOKENS = {}

SESSION_ID_LEN = int(CONFIG.get("WIRE_SESSION_ID_LEN", 16))


# Exception types
class HeaderMismatch(Exception):
    """Header validation failed (version, IDs, or session_id mismatch)."""
    pass


class AeadAuthError(Exception):
    """AEAD authentication failed during decryption."""
    pass


class ReplayError(Exception):
    """Packet replay detected or outside acceptable window."""
    pass


# Constants
HEADER_STRUCT = f"!BBBBB{SESSION_ID_LEN}sQB"
# Compute header length from structure to avoid drift when struct changes.
HEADER_LEN = struct.calcsize(HEADER_STRUCT)
# IV is still logically 12 bytes (1 epoch + 11 seq bytes) but is NO LONGER transmitted on wire.
# Wire format: header || ciphertext+tag
IV_LEN = 0  # length of IV bytes present on wire (0 after optimization)

# Maximum acceptable wire length.  UDP datagrams cannot exceed 65535.
# This guards against unreasonable buffers from non-UDP callers.
MAX_WIRE_LEN = 65536


def _zero_mutable_buffer(buf) -> None:
    if isinstance(buf, memoryview):
        buf = buf.cast("B")
    if isinstance(buf, bytearray):
        for index in range(len(buf)):
            buf[index] = 0




def _canonicalize_aead_token(token: str) -> str:
    candidate = token.lower()
    if candidate in _RETIRED_AEAD_TOKENS:
        raise ValueError(f"AEAD token '{token}' is retired: {_RETIRED_AEAD_TOKENS[candidate]}")
    candidate = _AEAD_TOKEN_ALIASES.get(candidate, candidate)
    if candidate not in _SUPPORTED_AEAD_TOKENS:
        raise ValueError(f"unknown AEAD token: {token}")
    return candidate


def required_key_length_for_aead(token: str) -> int:
    """Return the required key material length in bytes for the AEAD token."""

    normalized = _canonicalize_aead_token(token)
    if normalized in {"aesgcm128", "aesccm128", "ascon128"}:
        return 16
    if normalized in {"aesgcm192", "aesccm192"}:
        return 24
    if normalized in {"aesgcm256", "aesccm256", "chacha20poly1305", "aegis256"}:
        return 32
    raise AeadError(f"unsupported AEAD token: {token}")


class _AsconAdapter:
    """Adapter for the standardized Ascon-AEAD128 native backend."""

    def __init__(self, key: bytes, variant: str):
        if len(key) < 16:
            raise ValueError("Ascon requires at least 16 bytes of key material")
        strict = bool(CONFIG.get("ASCON_STRICT_KEY_SIZE", False))
        if strict and len(key) != 16:
            raise ValueError("ASCON_STRICT_KEY_SIZE enabled: key must be exactly 16 bytes")
        self._key = bytearray(key[:16])
        if variant != "ascon128":
            raise ValueError(f"unsupported Ascon variant: {variant}")
        self._algo_str = "Ascon-AEAD128"
        if _ascon_module is None:
            raise ImportError("Ascon native backend unavailable: core.ascon_backend import failed")
        if not hasattr(_ascon_module, "encrypt") or not hasattr(_ascon_module, "decrypt"):
            raise ImportError("Ascon native backend unavailable: core.ascon_backend missing encrypt/decrypt")

        variant_name = self._algo_str

        def _native_encrypt(
            key_bytes: bytes,
            nonce_bytes: bytes,
            aad_bytes: bytes,
            plaintext_bytes: bytes,
            algo: str = variant_name,
        ) -> bytes:
            return _ascon_module.encrypt(
                key_bytes, nonce_bytes, aad_bytes, plaintext_bytes, algo
            )

        def _native_decrypt(
            key_bytes: bytes,
            nonce_bytes: bytes,
            aad_bytes: bytes,
            ciphertext_bytes: bytes,
            algo: str = variant_name,
        ) -> bytes:
            result = _ascon_module.decrypt(
                key_bytes, nonce_bytes, aad_bytes, ciphertext_bytes, algo
            )
            if result is None:
                raise InvalidTag("Ascon authentication failed")
            return result

        self._enc = _native_encrypt
        self._dec = _native_decrypt

    def encrypt(self, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
        # Standardized Ascon-AEAD128 uses 16-byte nonces. Our canonical nonce
        # is 12 bytes (1 epoch + 11 seq), so we extend it with a zero suffix
        # before passing it to the backend.
        if len(nonce) < 16:
            nonce = nonce + b"\x00" * (16 - len(nonce))
        return self._enc(bytes(self._key), nonce[:16], aad, plaintext)

    def decrypt(self, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
        # Same zero-padding as encrypt() — see comment there for rationale.
        if len(nonce) < 16:
            nonce = nonce + b"\x00" * (16 - len(nonce))
        pt = self._dec(bytes(self._key), nonce[:16], aad, ciphertext)
        if pt is None:
            raise InvalidTag("Ascon authentication failed")
        return pt

    def destroy(self) -> None:
        _zero_mutable_buffer(self._key)


class _Aegis256Adapter:
    """AEGIS-256 AEAD adapter via libsodium (pysodium bindings).

    AEGIS-256 is an AES-round\u2013based AEAD designed for high throughput on
    hardware with AES-NI.  On platforms WITHOUT AES instructions (e.g.
    Cortex-A72 / RPi4) it falls back to a scalar software AES (softaes)
    implementation and is significantly slower (~10x vs AES-GCM).

    Parameters:
        key  \u2013 32 bytes (256-bit key)
    Nonce:   32 bytes
    Tag:     32 bytes (appended to ciphertext by libsodium)
    """

    _NONCE_LEN = 32
    _TAG_LEN = 32

    def __init__(self, key: bytes) -> None:
        if _pysodium_module is None:
            raise ImportError(
                "pysodium not available \u2013 install with: pip install pysodium  "
                "(requires libsodium >= 1.0.19 for AEGIS-256)"
            )
        if len(key) < 32:
            raise ValueError("AEGIS-256 requires >= 32-byte key material")
        self._key = bytearray(key[:32])

    def encrypt(self, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
        if len(nonce) < self._NONCE_LEN:
            nonce = nonce + b"\x00" * (self._NONCE_LEN - len(nonce))
        nonce = nonce[: self._NONCE_LEN]
        return _pysodium_module.crypto_aead_aegis256_encrypt(
            plaintext, aad, nonce, bytes(self._key)
        )

    def decrypt(self, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
        if len(nonce) < self._NONCE_LEN:
            nonce = nonce + b"\x00" * (self._NONCE_LEN - len(nonce))
        nonce = nonce[: self._NONCE_LEN]
        try:
            return _pysodium_module.crypto_aead_aegis256_decrypt(
                ciphertext, aad, nonce, bytes(self._key)
            )
        except Exception as exc:
            raise InvalidTag("AEGIS-256 authentication failed") from exc

    def destroy(self) -> None:
        _zero_mutable_buffer(self._key)


def _instantiate_aead(token: str, key: bytes) -> Tuple[object, int]:
    """Return AEAD primitive and required nonce length for the suite token."""

    normalized = _canonicalize_aead_token(token)
    required_len = required_key_length_for_aead(normalized)

    if normalized in {"aesgcm128", "aesgcm192", "aesgcm256"}:
        if len(key) != required_len:
            raise ValueError(f"{normalized.upper()} requires {required_len}-byte key material")
        return AESGCM(key), 12

    if normalized in {"aesccm128", "aesccm192", "aesccm256"}:
        if len(key) != required_len:
            raise ValueError(f"{normalized.upper()} requires {required_len}-byte key material")
        # Use 16-byte tag and 12-byte nonce for parity with our wire nonce layout.
        return AESCCM(key, tag_length=16), 12

    if normalized == "chacha20poly1305":
        if len(key) != required_len:
            raise ValueError("ChaCha20-Poly1305 requires 32-byte key material")
        return ChaCha20Poly1305(key), 12

    if normalized == "ascon128":
        return _AsconAdapter(key, normalized), 16

    if normalized == "aegis256":
        return _Aegis256Adapter(key), 32

    raise AeadError(f"unsupported AEAD token: {token}")


def _build_nonce(epoch: int, seq: int, nonce_len: int) -> bytes:
    base = bytes([epoch & 0xFF]) + seq.to_bytes(11, "big")
    if nonce_len == 12:
        return base
    if nonce_len > 12:
        return base + b"\x00" * (nonce_len - 12)
    raise ValueError("nonce length must be >= 12 bytes")


@dataclass(frozen=True)
class AeadIds:
    kem_id: int
    kem_param: int
    sig_id: int
    sig_param: int

    def __post_init__(self):
        for field_name, value in [("kem_id", self.kem_id), ("kem_param", self.kem_param), 
                                  ("sig_id", self.sig_id), ("sig_param", self.sig_param)]:
            if not isinstance(value, int) or not (0 <= value <= 255):
                raise ValueError(f"{field_name} must be int in range 0-255")


@dataclass
class Sender:
    """AEAD sender with deterministic nonce.

    NOT thread-safe: callers must hold an external lock (e.g. context_lock
    in async_proxy) if encrypt() may be invoked from multiple threads.
    """
    version: int
    ids: AeadIds
    session_id: bytes
    epoch: int
    key_send: bytes
    aead_token: str = "aesgcm"
    _seq: int = 0

    def __post_init__(self):
        if not isinstance(self.version, int) or self.version != CONFIG["WIRE_VERSION"]:
            raise ValueError(f"version must equal CONFIG WIRE_VERSION ({CONFIG['WIRE_VERSION']})")
        
        if not isinstance(self.ids, AeadIds):
            raise TypeError("ids must be AeadIds instance")
        
        if not isinstance(self.session_id, bytes) or len(self.session_id) != SESSION_ID_LEN:
            raise ValueError(f"session_id must be exactly {SESSION_ID_LEN} bytes")
        
        if not isinstance(self.epoch, int) or not (0 <= self.epoch <= 255):
            raise ValueError("epoch must be int in range 0-255")
        
        if not isinstance(self.key_send, (bytes, bytearray)):
            raise TypeError("key_send must be bytes or bytearray")
        # Store as mutable bytearray so callers can zero key material
        # after rekey (WireGuard keypair_destroy pattern, see F4).
        self.key_send = bytearray(self.key_send)
        
        if not isinstance(self._seq, int) or self._seq < 0:
            raise ValueError("_seq must be non-negative int")

        self._aead_token = _canonicalize_aead_token(self.aead_token)
        self._cipher, self._nonce_len = _instantiate_aead(self._aead_token, bytes(self.key_send))

    @property
    def seq(self):
        """Current sequence number."""
        return self._seq

    def pack_header(self, seq: int) -> bytes:
        """Pack header with given sequence number."""
        if not isinstance(seq, int) or seq < 0:
            raise ValueError("seq must be non-negative int")
        
        return struct.pack(
            HEADER_STRUCT,
            self.version,
            self.ids.kem_id,
            self.ids.kem_param, 
            self.ids.sig_id,
            self.ids.sig_param,
            self.session_id,
            seq,
            self.epoch
        )

    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt plaintext returning: header || ciphertext + tag.

        Deterministic IV (epoch||seq) is derived locally and NOT sent on wire to
        reduce overhead (saves 12 bytes per packet). Receiver reconstructs it.
        """
        if not isinstance(plaintext, (bytes, bytearray)):
            raise TypeError("plaintext must be bytes or bytearray")
        
        # BUG-4 fix: check destroy() sentinel before threshold arithmetic.
        # destroy() sets _seq = -1 and _cipher = None; without this guard the
        # threshold comparison (-1 >= 2^63) passes silently, and the failure
        # only surfaces as a confusing ValueError("seq must be non-negative int")
        # from pack_header instead of a clear AeadError.
        if self._seq < 0 or self._cipher is None:
            raise AeadError("sender destroyed: encrypt() called after destroy()")
        
        # Proactive rekey threshold to avoid IV exhaustion.
        # Default threshold is 2^31 as a safe conservative bound for AES-GCM and ChaCha20.
        # It ensures keys are rotated well before cryptographic limits are approached.
        try:
            threshold = int(CONFIG.get("REKEY_SEQ_THRESHOLD", 1 << 31))
        except Exception:
            threshold = 1 << 31
        if self._seq >= threshold:
            raise SequenceOverflow("approaching IV exhaustion; trigger rekey")
        
        # Pack header with current sequence
        header = self.pack_header(self._seq)

        iv = _build_nonce(self.epoch, self._seq, self._nonce_len)

        try:
            ciphertext = self._cipher.encrypt(iv, plaintext, header)
        except Exception as e:
            raise AeadError(f"AEAD encryption failed: {e}")
        
        # Increment sequence on success
        self._seq += 1
        
        # Return optimized wire format: header || ciphertext+tag (IV omitted)
        return header + ciphertext

    def bump_epoch(self) -> None:
        """Increase epoch and reset sequence.

        Safety policy: forbid wrapping 255->0 with the same key to avoid IV reuse.
        Callers should perform a new handshake to rotate keys before wrap.
        """
        if self.epoch == 255:
            raise AeadError("epoch wrap forbidden without rekey; perform handshake to rotate keys")
        self.epoch += 1
        self._seq = 0

    def destroy(self) -> None:
        """Zero key material and invalidate this Sender.

        After calling destroy(), any further encrypt() call will raise AeadError.
        This follows the WireGuard keypair_destroy pattern: zero the key bytes
        stored in the Python-level bytearray.  The AESGCM/ChaCha20 internal C
        heap copy cannot be reached from Python (see F4 comment in async_proxy).
        """
        _zero_mutable_buffer(self.key_send)
        if hasattr(self._cipher, "destroy"):
            try:
                self._cipher.destroy()
            except Exception:
                pass
        self._cipher = None
        self._seq = -1  # sentinel: encrypt() will fail on negative seq


@dataclass
class Receiver:
    """AEAD receiver with replay window.

    NOT thread-safe: callers must hold an external lock if decrypt()
    may be invoked from multiple threads.
    """
    version: int
    ids: AeadIds
    session_id: bytes
    epoch: int
    key_recv: bytes
    window: int
    strict_mode: bool = False  # True = raise exceptions, False = return None
    aead_token: str = "aesgcm"
    _high: int = -1
    _mask: int = 0

    def __post_init__(self):
        if not isinstance(self.version, int) or self.version != CONFIG["WIRE_VERSION"]:
            raise ValueError(f"version must equal CONFIG WIRE_VERSION ({CONFIG['WIRE_VERSION']})")
        
        if not isinstance(self.ids, AeadIds):
            raise TypeError("ids must be AeadIds instance")
        
        if not isinstance(self.session_id, bytes) or len(self.session_id) != SESSION_ID_LEN:
            raise ValueError(f"session_id must be exactly {SESSION_ID_LEN} bytes")
        
        if not isinstance(self.epoch, int) or not (0 <= self.epoch <= 255):
            raise ValueError("epoch must be int in range 0-255")
        
        if not isinstance(self.key_recv, (bytes, bytearray)):
            raise TypeError("key_recv must be bytes or bytearray")
        # Store as mutable bytearray so callers can zero key material
        # after rekey (WireGuard keypair_destroy pattern, see F4).
        self.key_recv = bytearray(self.key_recv)
        
        if not isinstance(self.window, int) or self.window < 64 or self.window > 65536:
            raise ValueError("window must be int in range 64..65536")
        
        if not isinstance(self._high, int):
            raise TypeError("_high must be int")
        
        if not isinstance(self._mask, int) or self._mask < 0:
            raise ValueError("_mask must be non-negative int")

        self._aead_token = _canonicalize_aead_token(self.aead_token)
        self._cipher, self._nonce_len = _instantiate_aead(self._aead_token, bytes(self.key_recv))
        self._last_error: Optional[str] = None

    def _check_replay(self, seq: int) -> None:
        """Check if sequence number WOULD be accepted (anti-replay pre-check).

        IMPORTANT: This only rejects obvious duplicates and too-old packets.
        It does NOT advance the window — that happens in _commit_replay()
        AFTER AEAD authentication succeeds.

        Rationale (WireGuard / RFC 6479 pattern): If window advancement
        happens before auth, an attacker can forge a packet with a high
        sequence number.  The window shifts forward and all legitimate
        in-flight packets are rejected as "too old".  By splitting into
        check (pre-auth) and commit (post-auth) we prevent this.
        """
        if seq > self._high:
            # Future packet — will be accepted if auth passes.
            return
        elif seq > self._high - self.window:
            # Within window — check if already seen
            offset = self._high - seq
            if self._mask & (1 << offset):
                raise ReplayError(f"duplicate packet seq={seq}")
            # Not yet seen — will be accepted if auth passes.
        else:
            # Too old — outside window
            raise ReplayError(f"packet too old seq={seq}, high={self._high}, window={self.window}")

    def _commit_replay(self, seq: int) -> None:
        """Advance replay window after AEAD authentication succeeds.

        Must only be called after decrypt verified the tag.
        See _check_replay() docstring for security rationale.
        """
        if seq > self._high:
            shift = seq - self._high
            if shift >= self.window:
                self._mask = 1
            else:
                self._mask = (self._mask << shift) | 1
                self._mask &= (1 << self.window) - 1
            self._high = seq
        elif seq > self._high - self.window:
            offset = self._high - seq
            self._mask |= (1 << offset)

    def decrypt(self, wire: bytes) -> Optional[bytes]:
        """Validate header, perform anti-replay, reconstruct IV, decrypt.

        Returns plaintext bytes or None (silent mode) on failure.
        """
        if self._cipher is None:
            raise AeadError("receiver destroyed: decrypt() called after destroy()")

        if not isinstance(wire, (bytes, bytearray)):
            raise ValueError("wire must be bytes or bytearray")
        
        if len(wire) < HEADER_LEN:
            raise ValueError("wire too short for header")

        if len(wire) > MAX_WIRE_LEN:
            raise ValueError(f"wire too large ({len(wire)} > {MAX_WIRE_LEN})")
        
        # Extract header
        header = wire[:HEADER_LEN]
        
        # Unpack and validate header
        try:
            fields = struct.unpack(HEADER_STRUCT, header)
            version, kem_id, kem_param, sig_id, sig_param, session_id, seq, epoch = fields
        except struct.error as e:
            raise ValueError(f"header unpack failed: {e}")
        
        # Validate header fields
        if version != self.version:
            self._last_error = "header"
            if self.strict_mode:
                raise HeaderMismatch(f"version mismatch: expected {self.version}, got {version}")
            return None
        
        if (kem_id, kem_param, sig_id, sig_param) != (self.ids.kem_id, self.ids.kem_param, self.ids.sig_id, self.ids.sig_param):
            self._last_error = "header"
            if self.strict_mode:
                raise HeaderMismatch(f"crypto ID mismatch")
            return None
        
        if session_id != self.session_id:
            self._last_error = "session"
            if self.strict_mode:
                raise HeaderMismatch("session_id mismatch")
            return None  # Wrong session - always fail silently for security
        
        if epoch != self.epoch:
            self._last_error = "session"
            if self.strict_mode:
                raise HeaderMismatch("epoch mismatch")
            return None  # Wrong epoch - always fail silently for rekeying
        
        # Tentative replay check — rejects obvious duplicates/too-old
        # but does NOT advance window (WireGuard / RFC 6479 pattern).
        try:
            self._check_replay(seq)
        except ReplayError:
            self._last_error = "replay"
            if self.strict_mode:
                raise
            return None
        
        # Reconstruct deterministic IV instead of reading from wire
        iv = _build_nonce(epoch, seq, self._nonce_len)
        ciphertext = wire[HEADER_LEN:]
        
        # Decrypt with header as AAD
        try:
            plaintext = self._cipher.decrypt(iv, ciphertext, header)
        except InvalidTag:
            # Auth failed — do NOT commit replay window advancement.
            # This prevents an attacker from shifting our window with
            # forged high-seq packets.
            self._last_error = "auth"
            if self.strict_mode:
                raise AeadAuthError("AEAD authentication failed")
            return None
        except Exception as e:
            raise AeadError(f"AEAD decryption failed: {e}")

        # Auth succeeded — NOW commit the window advancement.
        self._commit_replay(seq)
        self._last_error = None
        return plaintext

    def reset_replay(self) -> None:
        """Clear replay protection state."""
        self._high = -1
        self._mask = 0

    def bump_epoch(self) -> None:
        """Increase epoch and reset replay state.
        
        Safety policy: forbid wrapping 255->0 with the same key to avoid IV reuse.
        Callers should perform a new handshake to rotate keys before wrap.
        """
        if self.epoch == 255:
            raise AeadError("epoch wrap forbidden without rekey; perform handshake to rotate keys")
        self.epoch += 1
        self.reset_replay()

    def last_error_reason(self) -> Optional[str]:
        return getattr(self, "_last_error", None)

    def destroy(self) -> None:
        """Zero key material and invalidate this Receiver.

        After calling destroy(), any further decrypt() call will raise AeadError.
        Same limitations as Sender.destroy() regarding C-heap key copies.
        """
        _zero_mutable_buffer(self.key_recv)
        if hasattr(self._cipher, "destroy"):
            try:
                self._cipher.destroy()
            except Exception:
                pass
        self._cipher = None
        self._high = -1
        self._mask = 0


# Standalone Ascon-128 AEAD Helper Functions
try:
    import ascon as _py_ascon
except ImportError:
    _py_ascon = None


def ascon_encrypt(key: bytes, nonce: bytes, plaintext: bytes, associated_data: bytes = b"") -> Tuple[bytes, bytes]:
    """Encrypt payload using Ascon-128 AEAD and return (ciphertext, tag)."""
    key16 = (key[:16] + b"\x00" * 16)[:16]
    nonce16 = (nonce[:16] + b"\x00" * 16)[:16]
    if _py_ascon is not None:
        ct_tag = _py_ascon.encrypt(key16, nonce16, associated_data, plaintext, variant="Ascon-128")
        return ct_tag[:-16], ct_tag[-16:]
    elif _ascon_module is not None:
        adapter = _AsconAdapter(key16, "ascon128")
        ct_tag = adapter.encrypt(nonce16, plaintext, associated_data)
        return ct_tag[:-16], ct_tag[-16:]
    else:
        # Fallback to AES-128-GCM if Ascon native module is unavailable
        aesgcm = AESGCM(key16)
        ct_tag = aesgcm.encrypt(nonce16[:12], plaintext, associated_data)
        return ct_tag[:-16], ct_tag[-16:]


def ascon_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes, associated_data: bytes = b"") -> bytes:
    """Decrypt payload using Ascon-128 AEAD."""
    key16 = (key[:16] + b"\x00" * 16)[:16]
    nonce16 = (nonce[:16] + b"\x00" * 16)[:16]
    ct_tag = ciphertext + tag
    if _py_ascon is not None:
        return _py_ascon.decrypt(key16, nonce16, associated_data, ct_tag, variant="Ascon-128")
    elif _ascon_module is not None:
        adapter = _AsconAdapter(key16, "ascon128")
        return adapter.decrypt(nonce16, ct_tag, associated_data)
    else:
        aesgcm = AESGCM(key16)
        return aesgcm.decrypt(nonce16[:12], ct_tag, associated_data)

