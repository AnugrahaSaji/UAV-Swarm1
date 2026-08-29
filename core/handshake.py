from dataclasses import dataclass, field
import hashlib
import hmac
import os
import struct
import time
from typing import Dict, Optional, Tuple
from core.config import CONFIG
from core.aead import required_key_length_for_aead
from core.suites import get_suite
from core.logging_utils import get_logger

KeyEncapsulation = None
Signature = None

def _try_import_oqs():
    global KeyEncapsulation, Signature
    try:
        from oqs.oqs import KeyEncapsulation, Signature
        if KeyEncapsulation is not None and Signature is not None:
            return True
    except Exception:
        pass
    try:
        from oqs import KeyEncapsulation, Signature
        if KeyEncapsulation is not None and Signature is not None:
            return True
    except Exception:
        pass
    try:
        import oqs
        KeyEncapsulation = getattr(oqs, "KeyEncapsulation", None)
        Signature = getattr(oqs, "Signature", None)
        if KeyEncapsulation and Signature:
            return True
    except Exception:
        pass
    return False

if not _try_import_oqs():
    import sys
    from pathlib import Path
    home = Path.home()

    so_paths = [
        "/usr/local/lib",
        "/usr/local/lib64",
        str(home / "liboqs" / "build" / "lib"),
        str(home / "quantum-safe" / "liboqs" / "build" / "lib"),
    ]
    curr_ld = os.getenv("LD_LIBRARY_PATH", "")
    for p in so_paths:
        if os.path.isdir(p) and p not in curr_ld:
            curr_ld = f"{p}:{curr_ld}" if curr_ld else p
    os.environ["LD_LIBRARY_PATH"] = curr_ld

    candidates = [
        os.getenv("LIBOQS_PYTHON_DIR"),
        home / "liboqs-python",
        home / "quantum-safe" / "liboqs-python",
        home / "UAV-Swarm1" / "liboqs-python",
        Path("/home/swarmmain/liboqs-python"),
        Path("/home/dev/quantum-safe/liboqs-python"),
    ]
    for cand in candidates:
        if cand and Path(cand).is_dir() and str(cand) not in sys.path:
            sys.path.insert(0, str(cand))
            if _try_import_oqs():
                break

from core.exceptions import HandshakeError, HandshakeFormatError, HandshakeVerifyError

# ── Key material lifecycle (WireGuard / liboqs pattern) ─────────────────────
# WireGuard zeros all intermediate key material immediately after deriving
# session keys.  liboqs uses OQS_MEM_cleanse via memset-with-barrier.
# Python's immutable `bytes` can't be zeroed, but `bytearray` can.
# We use bytearray internally for secrets and wipe them after derivation.

_MAX_HANDSHAKE_MSG_BYTES = 2 * 1024 * 1024  # 2 MiB hard cap (amplification guard)
_SESSION_ID_LEN = int(CONFIG.get("WIRE_SESSION_ID_LEN", 16))
_CHALLENGE_LEN = 16
_AUTH_TAG_LEN = hashlib.sha256().digest_size
_KEY_CONFIRM_LEN = hashlib.sha256().digest_size


def _recv_exact(conn, byte_count: int, field_name: str) -> bytes:
    data = bytearray()
    while len(data) < byte_count:
        chunk = conn.recv(byte_count - len(data))
        if not chunk:
            raise ConnectionError(f"Connection closed reading {field_name}")
        data.extend(chunk)
    return bytes(data)


def _consume_slice(wire: bytes, offset: int, size: int, field_name: str) -> Tuple[bytes, int]:
    end = offset + size
    if end > len(wire):
        raise HandshakeFormatError(f"malformed server hello: truncated {field_name}")
    return wire[offset:end], end


def _build_server_transcript(version: int, session_id: bytes, kem_name: bytes, sig_name: bytes, kem_pub: bytes, challenge: bytes) -> bytes:
    return (
        struct.pack("!B", version)
        + b"|pq-drone-gcs:v2|"
        + session_id
        + b"|"
        + kem_name
        + b"|"
        + sig_name
        + b"|"
        + kem_pub
        + b"|"
        + challenge
    )


def _psk_digest(psk: bytes) -> bytes:
    if not isinstance(psk, (bytes, bytearray)) or len(psk) != 32:
        raise HandshakeVerifyError("DRONE_PSK must be exactly 32 bytes")
    return hashlib.sha256(b"pq-drone-gcs:psk:v2|" + bytes(psk)).digest()


def _build_key_confirmation_tag(confirm_key: bytes, label: bytes, hello_wire: bytes, kem_ct: bytes) -> bytes:
    transcript = label + b"|" + hello_wire + b"|" + kem_ct
    return hmac.new(confirm_key, transcript, hashlib.sha256).digest()


def _parse_server_hello_wire(wire: bytes, expected_version: int) -> Tuple[int, bytes, bytes, bytes, bytes, bytes, bytes]:
    try:
        offset = 0
        version = wire[offset]
        offset += 1
        if version != expected_version:
            raise HandshakeFormatError("bad wire version")

        kem_name_len = struct.unpack_from("!H", wire, offset)[0]
        offset += 2
        if kem_name_len <= 0:
            raise HandshakeFormatError("malformed server hello: empty kem_name")
        kem_name, offset = _consume_slice(wire, offset, kem_name_len, "kem_name")

        sig_name_len = struct.unpack_from("!H", wire, offset)[0]
        offset += 2
        if sig_name_len <= 0:
            raise HandshakeFormatError("malformed server hello: empty sig_name")
        sig_name, offset = _consume_slice(wire, offset, sig_name_len, "sig_name")

        session_id, offset = _consume_slice(wire, offset, _SESSION_ID_LEN, "session_id")
        challenge, offset = _consume_slice(wire, offset, _CHALLENGE_LEN, "challenge")

        kem_pub_len = struct.unpack_from("!I", wire, offset)[0]
        offset += 4
        if kem_pub_len <= 0 or kem_pub_len > _MAX_HANDSHAKE_MSG_BYTES:
            raise HandshakeFormatError("malformed server hello: invalid kem_pub length")
        kem_pub, offset = _consume_slice(wire, offset, kem_pub_len, "kem_pub")

        sig_len = struct.unpack_from("!H", wire, offset)[0]
        offset += 2
        if sig_len <= 0:
            raise HandshakeFormatError("malformed server hello: empty signature")
        signature, offset = _consume_slice(wire, offset, sig_len, "signature")
    except HandshakeFormatError:
        raise
    except Exception as exc:
        raise HandshakeFormatError(f"malformed server hello: {exc}") from exc

    if offset != len(wire):
        raise HandshakeFormatError("malformed server hello: trailing bytes present")

    return version, kem_name, sig_name, session_id, challenge, kem_pub, signature


def derive_transport_material(
    role: str,
    session_id: bytes,
    challenge: bytes,
    kem_name: bytes,
    sig_name: bytes,
    shared_secret: bytes,
    psk: bytes,
    *,
    metrics: Optional[Dict[str, object]] = None,
    epoch: int = 0,
):
    if role not in {"client", "server"}:
        raise HandshakeFormatError("invalid role")
    if not (isinstance(session_id, bytes) and len(session_id) == _SESSION_ID_LEN):
        raise HandshakeFormatError(f"session_id must be {_SESSION_ID_LEN} bytes")
    if not (isinstance(challenge, bytes) and len(challenge) == _CHALLENGE_LEN):
        raise HandshakeFormatError(f"challenge must be {_CHALLENGE_LEN} bytes")
    if not kem_name or not sig_name:
        raise HandshakeFormatError("kem_name/sig_name empty")
    try:
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes
    except ImportError:
        raise RuntimeError("cryptography not available")

    metrics_ref = metrics
    derive_wall_start = time.time_ns() if metrics_ref is not None else None
    derive_perf_start = time.perf_counter_ns() if metrics_ref is not None else None
    psk_mix = _psk_digest(psk)
    epoch_str = str(epoch).encode()
    info = b"pq-drone-gcs:kdf:v2|" + session_id + b"|" + challenge + b"|" + kem_name + b"|" + sig_name + b"|ep:" + epoch_str
    salt = hashlib.sha256(b"pq-drone-gcs|hkdf-salt|v2|" + session_id + challenge + psk_mix).digest()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=128,
        salt=salt,
        info=info,
    )
    okm = hkdf.derive(shared_secret)
    if metrics_ref is not None and derive_perf_start is not None and derive_wall_start is not None:
        derive_perf_end = time.perf_counter_ns()
        derive_wall_end = time.time_ns()
        prefix = "server" if role == "server" else "client"
        metrics_ref[f"kdf_{prefix}_ns"] = derive_perf_end - derive_perf_start
        metrics_ref[f"kdf_{prefix}_wall_start_ns"] = derive_wall_start
        metrics_ref[f"kdf_{prefix}_wall_end_ns"] = derive_wall_end
        metrics_ref["psk_bound_kdf"] = True
        metrics_ref["key_confirmation"] = "hmac-sha256"
    key_d2g = okm[:32]
    key_g2d = okm[32:64]
    client_confirm = okm[64:96]
    server_confirm = okm[96:128]

    if role == "client":
        return key_d2g, key_g2d, client_confirm, server_confirm
    return key_g2d, key_d2g, server_confirm, client_confirm

def derive_aead_ratchet(
    base_key_d2g: bytes,
    base_key_g2d: bytes,
    session_id: bytes,
    new_aead_id: str,
    epoch: int = 0,
) -> Tuple[bytes, bytes]:
    """
    Ratchets existing keys derived from the old handshake for a new AEAD profile.
    This skips liboqs and provides symmetric key material without PQC overhead.
    """
    try:
        from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
        from cryptography.hazmat.primitives import hashes
    except ImportError:
        raise RuntimeError("cryptography not available")

    # TLS 1.3 KeyUpdate style ratcheting with epoch binding:
    epoch_str = str(epoch).encode()
    key_len = required_key_length_for_aead(new_aead_id)
    
    hkdf_d2g = HKDFExpand(
        algorithm=hashes.SHA256(),
        length=key_len,
        info=b"pq-drone-gcs:ratchet|d2g|" + session_id + b"|" + new_aead_id.encode() + b"|ep:" + epoch_str,
    )
    new_k_d2g = hkdf_d2g.derive(base_key_d2g)

    hkdf_g2d = HKDFExpand(
        algorithm=hashes.SHA256(),
        length=key_len,
        info=b"pq-drone-gcs:ratchet|g2d|" + session_id + b"|" + new_aead_id.encode() + b"|ep:" + epoch_str,
    )
    new_k_g2d = hkdf_g2d.derive(base_key_g2d)

    return new_k_d2g, new_k_g2d

def _secure_zero(buf: bytearray) -> None:
    """Best-effort zeroing of mutable key material.

    Overwrites every byte with 0x00.  Does NOT protect against a
    hostile GC or swap-to-disk, but matches what WireGuard-go does
    for its Go-managed buffers.  For C-backed OQS objects, rely on
    oqs.KeyEncapsulation.free() which calls OQS_MEM_cleanse.
    """
    for i in range(len(buf)):
        buf[i] = 0

logger = get_logger("pqc")


def _ns_to_ms(value: object) -> float:
    try:
        ns = float(value)
    except (TypeError, ValueError):
        return 0.0
    if ns <= 0.0:
        return 0.0
    return round(ns / 1_000_000.0, 6)


def _finalize_handshake_metrics(metrics: Optional[Dict[str, object]]) -> None:
    """Augment handshake metrics with flattened Part B fields."""

    if not isinstance(metrics, dict):  # defensive guard
        return

    primitives = metrics.setdefault("primitives", {})
    if not isinstance(primitives, dict):
        primitives = {}
        metrics["primitives"] = primitives

    kem_metrics = primitives.setdefault("kem", {})
    if not isinstance(kem_metrics, dict):
        kem_metrics = {}
        primitives["kem"] = kem_metrics

    sig_metrics = primitives.setdefault("signature", {})
    if not isinstance(sig_metrics, dict):
        sig_metrics = {}
        primitives["signature"] = sig_metrics

    artifacts = metrics.setdefault("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
        metrics["artifacts"] = artifacts

    def _export_time(prefix: str, source: Dict[str, object], key: str, legacy_key: Optional[str] = None) -> float:
        ns_value = source.get(key)
        ms_value = _ns_to_ms(ns_value)
        metrics[f"{prefix}_max_ms"] = ms_value
        metrics[f"{prefix}_avg_ms"] = ms_value
        if legacy_key:
            metrics.setdefault(legacy_key, ms_value)
        return ms_value

    kem_keygen_ms = _export_time("kem_keygen", kem_metrics, "keygen_ns", "kem_keygen_ms")
    kem_encaps_ms = _export_time("kem_encaps", kem_metrics, "encap_ns", "kem_encaps_ms")
    kem_decaps_ms = _export_time("kem_decaps", kem_metrics, "decap_ns", "kem_decap_ms")
    sig_sign_ms = _export_time("sig_sign", sig_metrics, "sign_ns", "sig_sign_ms")
    sig_verify_ms = _export_time("sig_verify", sig_metrics, "verify_ns", "sig_verify_ms")

    metrics["pub_key_size_bytes"] = int(kem_metrics.get("public_key_bytes") or artifacts.get("public_key_bytes") or 0)
    metrics["ciphertext_size_bytes"] = int(kem_metrics.get("ciphertext_bytes") or 0)
    metrics["sig_size_bytes"] = int(sig_metrics.get("signature_bytes") or artifacts.get("signature_bytes") or 0)
    metrics["shared_secret_size_bytes"] = int(kem_metrics.get("shared_secret_bytes") or 0)

    handshake_total_ns = metrics.get("handshake_total_ns")
    metrics["rekey_ms"] = _ns_to_ms(handshake_total_ns)

    primitive_total = kem_keygen_ms + kem_encaps_ms + kem_decaps_ms + sig_sign_ms + sig_verify_ms
    metrics["primitive_total_ms"] = round(primitive_total, 6)

@dataclass(frozen=True)
class ServerHello:
    version: int
    kem_name: bytes
    sig_name: bytes
    session_id: bytes
    kem_pub: bytes
    signature: bytes
    challenge: bytes
    metrics: Optional[Dict[str, object]] = None

@dataclass
class ServerEphemeral:
    kem_name: str
    sig_name: str
    session_id: bytes
    kem_obj: object  # oqs.KeyEncapsulation instance
    challenge: bytes
    metrics: Dict[str, object] = field(default_factory=dict)

def build_server_hello(
    suite_id: str,
    server_sig_obj,
    *,
    metrics: Optional[Dict[str, object]] = None,
):
    if KeyEncapsulation is None or Signature is None:
        raise RuntimeError("oqs-python not available (KeyEncapsulation/Signature missing)")
    suite = get_suite(suite_id)
    if not suite:
        raise ValueError("suite_id not found")
    version = CONFIG["WIRE_VERSION"]
    kem_name = suite["kem_name"].encode("utf-8")
    sig_name = suite["sig_name"].encode("utf-8")
    if not kem_name or not sig_name:
        raise ValueError("kem_name/sig_name empty")
    if not hasattr(server_sig_obj, "sign"):
        raise TypeError("server_sig_obj must provide sign()")
    session_id = os.urandom(_SESSION_ID_LEN)
    challenge = os.urandom(_CHALLENGE_LEN)
    metrics_ref = metrics if metrics is not None else {}
    metrics_ref.setdefault("role", "gcs")
    metrics_ref.setdefault("suite_id", suite_id)
    metrics_ref.setdefault("kem_name", suite["kem_name"])
    metrics_ref.setdefault("sig_name", suite["sig_name"])
    primitives = metrics_ref.setdefault("primitives", {})
    kem_metrics = primitives.setdefault("kem", {})
    sig_metrics = primitives.setdefault("signature", {})
    artifacts = metrics_ref.setdefault("artifacts", {})

    keygen_wall_start = time.time_ns()
    keygen_perf_start = time.perf_counter_ns()
    kem_obj = KeyEncapsulation(kem_name.decode("utf-8"))
    kem_pub = kem_obj.generate_keypair()
    keygen_perf_end = time.perf_counter_ns()
    keygen_wall_end = time.time_ns()
    kem_metrics["keygen_ns"] = keygen_perf_end - keygen_perf_start
    kem_metrics["keygen_wall_start_ns"] = keygen_wall_start
    kem_metrics["keygen_wall_end_ns"] = keygen_wall_end
    kem_metrics["public_key_bytes"] = len(kem_pub)
    # Include negotiated wire version as first byte of transcript to prevent downgrade
    transcript = _build_server_transcript(version, session_id, kem_name, sig_name, kem_pub, challenge)
    sign_wall_start = time.time_ns()
    sign_perf_start = time.perf_counter_ns()
    signature = server_sig_obj.sign(transcript)
    sign_perf_end = time.perf_counter_ns()
    sign_wall_end = time.time_ns()
    sig_metrics["sign_ns"] = sign_perf_end - sign_perf_start
    sig_metrics["sign_wall_start_ns"] = sign_wall_start
    sig_metrics["sign_wall_end_ns"] = sign_wall_end
    sig_metrics["signature_bytes"] = len(signature)
    wire = struct.pack("!B", version)
    wire += struct.pack("!H", len(kem_name)) + kem_name
    wire += struct.pack("!H", len(sig_name)) + sig_name
    wire += session_id
    wire += challenge
    wire += struct.pack("!I", len(kem_pub)) + kem_pub
    wire += struct.pack("!H", len(signature)) + signature
    artifacts["server_hello_bytes"] = len(wire)
    artifacts.setdefault("public_key_bytes", len(kem_pub))
    artifacts.setdefault("signature_bytes", len(signature))
    artifacts.setdefault("challenge_bytes", len(challenge))
    ephemeral = ServerEphemeral(
        kem_name=kem_name.decode("utf-8"),
        sig_name=sig_name.decode("utf-8"),
        session_id=session_id,
        kem_obj=kem_obj,
        challenge=challenge,
        metrics=metrics_ref,
    )
    return wire, ephemeral

def parse_and_verify_server_hello(
    wire: bytes,
    expected_version: int,
    server_sig_pub: bytes,
    *,
    metrics: Optional[Dict[str, object]] = None,
) -> ServerHello:
    if Signature is None:
        raise RuntimeError("oqs-python not available (Signature missing)")
    try:
        version, kem_name, sig_name, session_id, challenge, kem_pub, signature = _parse_server_hello_wire(wire, expected_version)
    except HandshakeFormatError:
        raise
    transcript = _build_server_transcript(version, session_id, kem_name, sig_name, kem_pub, challenge)
    metrics_ref = metrics
    if metrics_ref is not None:
        metrics_ref.setdefault("role", metrics_ref.get("role", "drone"))
        primitives = metrics_ref.setdefault("primitives", {})
        sig_metrics = primitives.setdefault("signature", {})
        kem_metrics = primitives.setdefault("kem", {})
        kem_metrics.setdefault("public_key_bytes", len(kem_pub))
        artifacts_ref = metrics_ref.setdefault("artifacts", {})
        artifacts_ref.setdefault("public_key_bytes", len(kem_pub))
    else:
        sig_metrics = None
    sig = None
    try:
        verify_wall_start = time.time_ns() if sig_metrics is not None else None
        verify_perf_start = time.perf_counter_ns() if sig_metrics is not None else None
        if Signature is None:
            raise RuntimeError("oqs-python not available (Signature missing)")
        sig = Signature(sig_name.decode("utf-8"))
        if not sig.verify(transcript, signature, server_sig_pub):
            raise HandshakeVerifyError("bad signature")
        if sig_metrics is not None and verify_perf_start is not None and verify_wall_start is not None:
            verify_perf_end = time.perf_counter_ns()
            verify_wall_end = time.time_ns()
            sig_metrics["verify_ns"] = verify_perf_end - verify_perf_start
            sig_metrics["verify_wall_start_ns"] = verify_wall_start
            sig_metrics["verify_wall_end_ns"] = verify_wall_end
            sig_metrics["signature_bytes"] = len(signature)
    except HandshakeVerifyError:
        raise
    except Exception as exc:
        raise HandshakeVerifyError(f"signature verification failed: {exc}") from exc
    finally:
        if sig is not None and hasattr(sig, "free"):
            try:
                sig.free()
            except Exception:
                pass
    return ServerHello(
        version=version,
        kem_name=kem_name,
        sig_name=sig_name,
        session_id=session_id,
        kem_pub=kem_pub,
        signature=signature,
        challenge=challenge,
        metrics=metrics_ref,
    )

def _drone_psk_bytes() -> bytes:
    psk_hex = os.getenv("DRONE_PSK", CONFIG.get("DRONE_PSK", ""))
    if not psk_hex:
        raise RuntimeError("DRONE_PSK must be provided and decode to 32 bytes")
    try:
        psk = bytes.fromhex(psk_hex)
    except ValueError as exc:
        raise ValueError(f"Invalid DRONE_PSK hex: {exc}")
    if len(psk) != 32:
        raise ValueError("DRONE_PSK must decode to 32 bytes")
    return psk


def client_encapsulate(server_hello: ServerHello, *, metrics: Optional[Dict[str, object]] = None):
    kem = None
    try:
        if KeyEncapsulation is None:
            raise RuntimeError("oqs-python not available (KeyEncapsulation missing)")
        kem = KeyEncapsulation(server_hello.kem_name.decode("utf-8"))
        metrics_ref = metrics if metrics is not None else getattr(server_hello, "metrics", None)
        encap_wall_start = time.time_ns() if metrics_ref is not None else None
        encap_perf_start = time.perf_counter_ns() if metrics_ref is not None else None
        kem_ct, shared_secret = kem.encap_secret(server_hello.kem_pub)
        if metrics_ref is not None and encap_perf_start is not None and encap_wall_start is not None:
            encap_perf_end = time.perf_counter_ns()
            encap_wall_end = time.time_ns()
            primitives = metrics_ref.setdefault("primitives", {})
            kem_metrics = primitives.setdefault("kem", {})
            kem_metrics["encap_ns"] = encap_perf_end - encap_perf_start
            kem_metrics["encap_wall_start_ns"] = encap_wall_start
            kem_metrics["encap_wall_end_ns"] = encap_wall_end
            kem_metrics["ciphertext_bytes"] = len(kem_ct)
            kem_metrics.setdefault("shared_secret_bytes", len(shared_secret))
        return kem_ct, shared_secret
    except Exception as exc:
        raise HandshakeError(f"client_encapsulate failed: {exc}") from exc
    finally:
        if kem is not None and hasattr(kem, "free"):
            try:
                kem.free()
            except Exception:
                pass


def server_decapsulate(
    ephemeral: ServerEphemeral,
    kem_ct: bytes,
    *,
    metrics: Optional[Dict[str, object]] = None,
):
    kem_obj = getattr(ephemeral, "kem_obj", None)
    try:
        if kem_obj is None:
            raise HandshakeError("server_decapsulate missing kem_obj")
        metrics_ref = metrics if metrics is not None else getattr(ephemeral, "metrics", None)
        decap_wall_start = time.time_ns() if metrics_ref is not None else None
        decap_perf_start = time.perf_counter_ns() if metrics_ref is not None else None
        shared_secret = kem_obj.decap_secret(kem_ct)
        if metrics_ref is not None and decap_perf_start is not None and decap_wall_start is not None:
            decap_perf_end = time.perf_counter_ns()
            decap_wall_end = time.time_ns()
            primitives = metrics_ref.setdefault("primitives", {})
            kem_metrics = primitives.setdefault("kem", {})
            kem_metrics["decap_ns"] = decap_perf_end - decap_perf_start
            kem_metrics["decap_wall_start_ns"] = decap_wall_start
            kem_metrics["decap_wall_end_ns"] = decap_wall_end
            kem_metrics.setdefault("ciphertext_bytes", len(kem_ct))
            kem_metrics.setdefault("shared_secret_bytes", len(shared_secret))
        return shared_secret
    except Exception as exc:
        raise HandshakeError("server_decapsulate failed") from exc
    finally:
        if kem_obj is not None and hasattr(kem_obj, "free"):
            try:
                kem_obj.free()
            except Exception:
                pass
        if hasattr(ephemeral, "kem_obj"):
            ephemeral.kem_obj = None


def derive_transport_keys(
    role: str,
    session_id: bytes,
    challenge: bytes,
    kem_name: bytes,
    sig_name: bytes,
    shared_secret: bytes,
    psk: bytes,
    *,
    metrics: Optional[Dict[str, object]] = None,
    epoch: int = 0,
):
    key_send, key_recv, _local_confirm, _peer_confirm = derive_transport_material(
        role,
        session_id,
        challenge,
        kem_name,
        sig_name,
        shared_secret,
        psk,
        metrics=metrics,
        epoch=epoch,
    )
    return key_send, key_recv
def server_gcs_handshake(conn, suite, gcs_sig_secret, *, timeout: float = 10.0, epoch: int = 0):
    """Authenticated GCS side handshake.

    Requires a ready oqs.Signature object (with generated key pair). Fails fast if not.
    """
    # OQS compatibility - get Signature class
    _Signature = None
    try:
        from oqs.oqs import Signature as _Signature
    except (ImportError, ModuleNotFoundError):
        try:
            from oqs import Signature as _Signature
        except (ImportError, ModuleNotFoundError):
            import oqs
            _Signature = oqs.Signature
    import struct

    try:
        conn.settimeout(float(timeout))
    except Exception:
        conn.settimeout(10.0)

    if _Signature is not None and not isinstance(gcs_sig_secret, _Signature):
        raise ValueError("gcs_sig_secret must be an oqs.Signature object with a loaded keypair")

    suite_id = suite.get("suite_id") if isinstance(suite, dict) else None
    if not suite_id:
        raise ValueError("suite must include suite_id")

    handshake_metrics: Dict[str, object] = {
        "role": "gcs",
        "suite_id": suite_id,
        "kem_name": suite.get("kem_name"),
        "sig_name": suite.get("sig_name"),
    }
    handshake_wall_start = time.time_ns()
    handshake_perf_start = time.perf_counter_ns()
    hello_wire, ephemeral = build_server_hello(suite_id, gcs_sig_secret, metrics=handshake_metrics)
    handshake_metrics["handshake_wall_start_ns"] = handshake_wall_start
    artifacts = handshake_metrics.setdefault("artifacts", {})
    artifacts.setdefault("server_hello_bytes", len(hello_wire))
    conn.sendall(struct.pack("!I", len(hello_wire)) + hello_wire)

    psk = _drone_psk_bytes()

    # Receive KEM ciphertext
    ct_len_bytes = _recv_exact(conn, 4, "ciphertext length")
    ct_len = struct.unpack("!I", ct_len_bytes)[0]
    # F3: KEM ciphertext allocation guard.  Largest PQC ciphertext in our
    # suite matrix is Classic McEliece ~240 bytes.  1 MiB is generous.
    if ct_len > _MAX_HANDSHAKE_MSG_BYTES:
        raise HandshakeFormatError(
            f"KEM ciphertext too large ({ct_len} bytes, max {_MAX_HANDSHAKE_MSG_BYTES})"
        )
    kem_ct = _recv_exact(conn, ct_len, "ciphertext")
    primitives = handshake_metrics.setdefault("primitives", {})
    kem_metrics = primitives.setdefault("kem", {})
    kem_metrics.setdefault("ciphertext_bytes", len(kem_ct))

    tag = _recv_exact(conn, _AUTH_TAG_LEN, "drone authentication tag")
    artifacts["auth_tag_bytes"] = len(tag)
    client_confirm = _recv_exact(conn, _KEY_CONFIRM_LEN, "client key confirmation tag")
    artifacts["client_confirm_bytes"] = len(client_confirm)

    expected_tag = hmac.new(psk, hello_wire, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        peer_ip = "unknown"
        try:
            peer_info = conn.getpeername()
            if isinstance(peer_info, tuple) and peer_info:
                peer_ip = str(peer_info[0])
            elif isinstance(peer_info, str) and peer_info:
                peer_ip = peer_info
        except (OSError, ValueError):
            peer_ip = "unknown"
        logger.warning(
            "Rejected drone handshake with bad authentication tag",
            extra={"role": "gcs", "expected_peer": CONFIG["DRONE_HOST"], "received": peer_ip},
        )
        raise HandshakeVerifyError("drone authentication failed")

    shared_secret = server_decapsulate(ephemeral, kem_ct, metrics=handshake_metrics)
    # Convert to mutable bytearray so we can zero after derivation
    _shared_secret_buf = bytearray(shared_secret)
    try:
        key_send, key_recv, server_confirm_key, client_confirm_key = derive_transport_material(
            "server",
            ephemeral.session_id,
            ephemeral.challenge,
            ephemeral.kem_name.encode("utf-8"),
            ephemeral.sig_name.encode("utf-8"),
            bytes(_shared_secret_buf),
            psk,
            metrics=handshake_metrics,
            epoch=epoch,
        )
        expected_client_confirm = _build_key_confirmation_tag(
            client_confirm_key,
            b"client",
            hello_wire,
            kem_ct,
        )
        if not hmac.compare_digest(client_confirm, expected_client_confirm):
            raise HandshakeVerifyError("drone key confirmation failed")
        server_confirm = _build_key_confirmation_tag(server_confirm_key, b"server", hello_wire, kem_ct)
        conn.sendall(server_confirm)
        artifacts["server_confirm_bytes"] = len(server_confirm)
    finally:
        _secure_zero(_shared_secret_buf)
        del _shared_secret_buf
    handshake_metrics["handshake_wall_end_ns"] = time.time_ns()
    handshake_metrics["handshake_total_ns"] = time.perf_counter_ns() - handshake_perf_start
    _finalize_handshake_metrics(handshake_metrics)
    return (
        key_recv,
        key_send,
        b"",
        b"",
        ephemeral.session_id,
        ephemeral.kem_name,
        ephemeral.sig_name,
        handshake_metrics,
    )

def client_drone_handshake(client_sock, suite, gcs_sig_public, *, timeout: float = 10.0, epoch: int = 0):
    # Real handshake implementation with MANDATORY signature verification
    import struct
    
    # Add socket timeout to prevent hanging
    try:
        client_sock.settimeout(float(timeout))
    except Exception:
        client_sock.settimeout(10.0)
    
    handshake_metrics: Dict[str, object] = {
        "role": "drone",
        "suite_id": suite.get("suite_id") if isinstance(suite, dict) else None,
        "kem_name": suite.get("kem_name") if isinstance(suite, dict) else None,
        "sig_name": suite.get("sig_name") if isinstance(suite, dict) else None,
    }
    handshake_wall_start = time.time_ns()
    handshake_perf_start = time.perf_counter_ns()

    # Receive server hello with length prefix
    hello_len_bytes = _recv_exact(client_sock, 4, "hello length")
    hello_len = struct.unpack("!I", hello_len_bytes)[0]
    # F3: Allocation bomb guard (WireGuard / QUIC amplification cap pattern).
    # Without this, a malicious GCS can send hello_len=0xFFFFFFFF and force
    # a 4 GiB allocation on the Pi, causing OOM-kill.  2 MiB covers even
    # Classic McEliece-8192128 (~1.3 MB public key).
    if hello_len > _MAX_HANDSHAKE_MSG_BYTES:
        raise HandshakeFormatError(
            f"server hello too large ({hello_len} bytes, max {_MAX_HANDSHAKE_MSG_BYTES})"
        )
    hello_wire = _recv_exact(client_sock, hello_len, "hello")
    artifacts = handshake_metrics.setdefault("artifacts", {})
    artifacts["server_hello_bytes"] = len(hello_wire)

    # Parse and VERIFY server hello - NO BYPASS ALLOWED
    # This is critical for security - verification failure must abort
    hello = parse_and_verify_server_hello(
        hello_wire,
        CONFIG["WIRE_VERSION"],
        gcs_sig_public,
        metrics=handshake_metrics,
    )

    expected_kem = suite.get("kem_name") if isinstance(suite, dict) else None
    expected_sig = suite.get("sig_name") if isinstance(suite, dict) else None
    negotiated_kem = hello.kem_name.decode("utf-8") if isinstance(hello.kem_name, bytes) else hello.kem_name
    negotiated_sig = hello.sig_name.decode("utf-8") if isinstance(hello.sig_name, bytes) else hello.sig_name
    if expected_kem and negotiated_kem != expected_kem:
        logger.error(
            "Suite mismatch",
            extra={
                "expected_kem": expected_kem,
                "expected_sig": expected_sig,
                "negotiated_kem": negotiated_kem,
                "negotiated_sig": negotiated_sig,
            },
        )
        raise HandshakeVerifyError(
            f"Downgrade attempt detected: expected {expected_kem}, got {negotiated_kem}"
        )
    if expected_sig and negotiated_sig != expected_sig:
        logger.error(
            "Suite mismatch",
            extra={
                "expected_kem": expected_kem,
                "expected_sig": expected_sig,
                "negotiated_kem": negotiated_kem,
                "negotiated_sig": negotiated_sig,
            },
        )
        raise HandshakeVerifyError(
            f"Downgrade attempt detected: expected {expected_sig}, got {negotiated_sig}"
        )

    # Encapsulate and send KEM ciphertext + authentication tag
    kem_ct, shared_secret = client_encapsulate(hello, metrics=handshake_metrics)
    # Convert to mutable bytearray so we can zero after derivation
    _shared_secret_buf = bytearray(shared_secret)
    psk = _drone_psk_bytes()
    primitives = handshake_metrics.setdefault("primitives", {})
    kem_metrics = primitives.setdefault("kem", {})
    kem_metrics.setdefault("ciphertext_bytes", len(kem_ct))
    kem_metrics.setdefault("shared_secret_bytes", len(shared_secret))
    tag = hmac.new(psk, hello_wire, hashlib.sha256).digest()
    try:
        key_send, key_recv, client_confirm_key, server_confirm_key = derive_transport_material(
            "client",
            hello.session_id,
            hello.challenge,
            hello.kem_name,
            hello.sig_name,
            bytes(_shared_secret_buf),
            psk,
            metrics=handshake_metrics,
            epoch=epoch,
        )
        client_confirm = _build_key_confirmation_tag(client_confirm_key, b"client", hello_wire, kem_ct)
        client_sock.sendall(struct.pack("!I", len(kem_ct)) + kem_ct + tag + client_confirm)
        artifacts["auth_tag_bytes"] = len(tag)
        artifacts["client_confirm_bytes"] = len(client_confirm)

        server_confirm = _recv_exact(client_sock, _KEY_CONFIRM_LEN, "server key confirmation tag")
        artifacts["server_confirm_bytes"] = len(server_confirm)
        expected_server_confirm = _build_key_confirmation_tag(server_confirm_key, b"server", hello_wire, kem_ct)
        if not hmac.compare_digest(server_confirm, expected_server_confirm):
            raise HandshakeVerifyError("gcs key confirmation failed")
    finally:
        _secure_zero(_shared_secret_buf)
        del _shared_secret_buf

    handshake_metrics["handshake_wall_start_ns"] = handshake_wall_start
    handshake_metrics["handshake_wall_end_ns"] = time.time_ns()
    handshake_metrics["handshake_total_ns"] = time.perf_counter_ns() - handshake_perf_start
    _finalize_handshake_metrics(handshake_metrics)

    # Return in expected format (nonce seeds are unused)
    return (
        key_send,
        key_recv,
        b"",
        b"",
        hello.session_id,
        hello.kem_name.decode() if isinstance(hello.kem_name, bytes) else hello.kem_name,
        hello.sig_name.decode() if isinstance(hello.sig_name, bytes) else hello.sig_name,
        handshake_metrics,
    )

