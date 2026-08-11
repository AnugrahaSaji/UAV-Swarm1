# Secure-Tunnel — Aggressive Multi-Source Validation Checklist
> Format: **REQUIREMENT | EXACT FUNCTION/API | NEGATIVE TEST | INVARIANT/LOG/ASSERTION**
>
> Sources confirmed in parallel from: RFC 5869, RFC 8446 §7.1/7.2, RFC 9001 §5/6, NIST SP 800-38D,
> OpenSSL docs (EVP_KDF-HKDF, EVP_KDF-TLS13_KDF, EVP_KEM-ML-KEM, EVP_PKEY-ML-KEM),
> and live codebase reads of core/handshake.py, core/aead.py, core/policy_engine.py, core/async_proxy.py.

---

## PHASE 0 — Baseline Lock

| # | REQUIREMENT | EXACT FUNCTION/API | NEGATIVE TEST | INVARIANT/LOG/ASSERTION |
|---|---|---|---|---|
| 0.1 | All 7 core modules must compile clean | `python -m py_compile core/suites.py core/policy_engine.py core/control_tcp.py core/async_proxy.py core/handshake.py core/aead.py sscheduler/policy.py sscheduler/benchmark_policy.py` | Introduce a deliberate SyntaxError in each file; verify each is caught independently | Zero output on stdout/stderr; exit code 0 for all |
| 0.2 | Optional backends fail gracefully — never crash import | `core/aead.py` fallback chain: `_ascon_native_module = None`, `_pysodium_module = None` | Remove oqs, pysodium, ascon from env; re-import module | Module imports cleanly; missing backends return `None`; only raises on first USE, not import |
| 0.3 | OQS import must use compatibility shim, never hard-require | `core/handshake.py` try/except chain for `KeyEncapsulation, Signature` | Uninstall oqs entirely | `KeyEncapsulation is None` — logged warning; `HandshakeError` raised on first KEM call, not at import |

---

## PHASE 1 — State Engine Split (core/policy_engine.py · Agent A)

| # | REQUIREMENT | EXACT FUNCTION/API | NEGATIVE TEST | INVARIANT/LOG/ASSERTION |
|---|---|---|---|---|
| 1.1 | `HandshakeState` must hold KEM/sig profile only — no AEAD fields | `HandshakeState(active_profile="kyber768_dilithium3")` | Store an AEAD token like `"aesgcm"` in `HandshakeState.active_profile` | Assert field semantics: only algorithm IDs that appear in `core/suites.py` KEM/sig slots are valid |
| 1.2 | `CipherState` must hold AEAD profile only — no KEM fields | `CipherState(active_profile="aesgcm")` | Store `"kyber768"` in `CipherState.active_profile` | Assert `_canonicalize_aead_token(state.cipher.active_profile)` succeeds for all saved AEAD tokens |
| 1.3 | Facade `ControlState.__post_init__` must wire both sub-states | `ControlState.__post_init__` → `self.handshake = HandshakeState(active_profile=self.current_suite)` | Build `ControlState` with `current_suite=""` (empty string) | `state.handshake.active_profile == state.cipher.active_profile == state.current_suite` immediately after construction |
| 1.4 | `request_prepare()` API must be unchanged for existing callers | `request_prepare(state: ControlState, suite_id: str, rid: str)` — imported by `async_proxy.py` | Call with `state.coordinator_role = "drone"` when role is also `"drone"` → non-coordinator must be rejected | `ControlResult.start_handshake` is `None` + note "not coordinator" when role is not coordinator |
| 1.5 | `record_rekey_result()` must update BOTH sub-states atomically | `record_rekey_result(state, rid, new_suite, success=True)` | Call with `success=False` — must not update active profiles | On success: `state.handshake.active_profile == new_suite` AND `state.cipher.active_profile == new_suite` AND `state.stats["rekeys_ok"] += 1` |
| 1.6 | Seen-RID replay guard must survive state split | `ControlState.seen_rids: deque(maxlen=256)` | Submit the same `rid` twice via `handle_control()` | Second call must return a `ControlResult` with a rejection note; `seen_rids` contains the RID |
| 1.7 | Coordinator role must reject unknown values | `set_coordinator_role(state, value)` calls `normalize_coordinator_role()` | Pass `"admin"`, `""`, `None`, `"\x00gcs\x00"` | Every non-`{"gcs","drone"}` value → `ValueError("invalid coordinator_role")` or normalized to default |

---

## PHASE 2 — OOB Control-Plane Hardening (core/control_tcp.py · Agent B)

| # | REQUIREMENT | EXACT FUNCTION/API | NEGATIVE TEST | INVARIANT/LOG/ASSERTION |
|---|---|---|---|---|
| 2.1 | TCP request handler must ONLY validate and enqueue — no crypto | grep `from oqs` / `from core.handshake` / `KeyEncapsulation` in `control_tcp.py` | Add a KEM call inside the request handler; run compile + grep | `grep -n "KeyEncapsulation\|oqs\|HKDF\|hkdf" core/control_tcp.py` returns zero matches |
| 2.2 | Coordinator restriction enforced before any negotiation intent is enqueued | `handle_control(state, message)` → checks `is_coordinator(state)` FIRST | Send a `PREPARE` message with `role="drone"` acting as coordinator | `ControlResult.start_handshake is None`; note logged "non-coordinator cannot initiate" |
| 2.3 | Allowlist check must gate peer acceptance | `server_gcs_handshake()` / `client_drone_handshake()` validates peer IP against allowlist before completing handshake | Submit handshake from an IP not in configured allowlist | Connection refused / `HandshakeVerifyError`; no key material derived |
| 2.4 | No key material must enter TCP request thread stack | Profile TCP handler thread; check for `bytes` of length 32 in frame locals | Temporarily log all local variables in handler; check for key-shaped bytes | No variable of length 32/64 matching a key pattern should be visible in handler locals |

---

## PHASE 3 — Soft-Transition Data Plane (core/async_proxy.py · Agent C)

| # | REQUIREMENT | EXACT FUNCTION/API | NEGATIVE TEST | INVARIANT/LOG/ASSERTION |
|---|---|---|---|---|
| 3.1 | New sender/receiver MUST be built OUTSIDE `context_lock` | `async_proxy.py` lines 1498-1508: `new_sender, new_receiver = _build_sender_receiver(...)` then `with context_lock:` | Time a full rekey under load — lock hold time must not include handshake duration | Lock hold time ≤ 1ms; handshake takes 10–100ms measured OUTSIDE lock |
| 3.2 | `cfg["SUITE_AEAD_TOKEN"]` swap must be INSIDE `context_lock` (atomic with sender/receiver swap) | `with context_lock: cfg["SUITE_AEAD_TOKEN"] = ...; active_context["sender"] = new_sender; active_context["receiver"] = new_receiver` | Simulate a concurrent decrypt call arriving mid-swap (race test with threading.Barrier) | No packet decrypted with mismatched token vs. receiver AEAD algorithm |
| 3.3 | Old sender/receiver key material must be zeroed after swap | `old_sender.destroy()` / `bytearray` key zeroing pattern; `_zero_mutable_buffer(old_sender.key_send)` | Rekey, then attempt to use old_sender.encrypt() | Raises `AeadError("sender destroyed: encrypt() called after destroy()")` |
| 3.4 | Replay window must reset on epoch change — no cross-epoch sequence bleed | `Receiver.bump_epoch()` resets `_high = -1` and `_mask = 0`; `Sender.bump_epoch()` resets `_seq = 0` | Send seq=1000 in epoch=1, then send seq=1 in epoch=2 | Epoch=2 seq=1 is accepted (fresh window, not confused with epoch=1 seq=1) |
| 3.5 | Dual-context accept window — old receiver still accepts in-flight packets during swap | Store previous-epoch `Receiver` in `active_context["prev_receiver"]` for N packets or T ms | Send 10 packets on old key, trigger rekey, send 10 more on old key | Old-key packets arriving ≤ window duration after swap are decrypted successfully; no blackout |
| 3.6 | Rekey blackout MUST be measurable and logged | `counters.rekey_blackout_duration_ms` set from `_rekey_blackout_end_mono - _rekey_blackout_start_mono` | Force telemetry in controlled local test; verify `rekey_blackout_duration_ms > 0` | `counters.rekey_blackout_duration_ms` is non-zero, non-negative; logged via `logger.info("rekey_blackout_ms=%f")` |
| 3.7 | Sequence overflow MUST trigger before nonce reuse — `REKEY_SEQ_THRESHOLD` ≤ 2^32 for AES-GCM | `CONFIG["REKEY_SEQ_THRESHOLD"]` = `1 << 32` in production AES-GCM config (NOT default 1 << 63) | Set `REKEY_SEQ_THRESHOLD = 1 << 63` (current default) and count packets | **CRITICAL**: With default 2^63, threshold is never reached for AES-GCM. **NIST SP 800-38D §B.1** requires ≤ 2^32 AES-GCM invocations per key. Configured threshold MUST be ≤ 2^32. |
| 3.8 | `SequenceOverflow` must be raised proactively, not silently swallowed | `Sender.encrypt()` at line: `if self._seq >= threshold: raise SequenceOverflow(...)` | Set `REKEY_SEQ_THRESHOLD = 5`; encrypt 6 packets | 6th call raises `SequenceOverflow("approaching IV exhaustion; trigger rekey")`; proxy triggers rekey, does NOT drop datagram silently |

---

## PHASE 4 — HKDF Ratchet for AEAD-only Shifts (core/handshake.py + async_proxy.py · Agent D)

| # | REQUIREMENT | EXACT FUNCTION/API | NEGATIVE TEST | INVARIANT/LOG/ASSERTION |
|---|---|---|---|---|
| 4.1 | `derive_transport_material()` uses full HKDF (extract + expand), 128-byte OKM | `HKDF(algorithm=hashes.SHA256(), length=128, salt=salt, info=info).derive(shared_secret)` | Pass `shared_secret = b""` | `ValueError` or `cryptography` raises on zero-length IKM; never produces a zero OKM |
| 4.2 | HKDF salt is protocol + session bound, not hardcoded | `salt = hashlib.sha256(b"pq-drone-gcs|hkdf-salt|v2|" + session_id + challenge + psk_mix).digest()` | Two sessions with different session_id/challenge must produce different salts | `salt_A != salt_B` for any two distinct `(session_id, challenge)` pairs |
| 4.3 | HKDF info MUST include all protocol-binding fields | info = `b"pq-drone-gcs:kdf:v2|" + session_id + b"|" + challenge + b"|" + kem_name + b"|" + sig_name` | Call with two different `kem_name` values but same everything else | Two different kem_names → two different OKMs; cross-algorithm key binding broken otherwise |
| 4.4 | HKDF info must be ≤ 1024 bytes | `len(info) <= 1024` | Construct info with kem_name = `b"X" * 1000` | `assert len(info) <= 1024` or an explicit guard before `HKDF.derive()` call; log if approaching limit |
| 4.5 | PSK must be exactly 32 bytes (≥ 256 bits — exceeds FIPS 112-bit minimum) | `_psk_digest(psk)` → `if len(psk) != 32: raise HandshakeVerifyError("DRONE_PSK must be exactly 32 bytes")` | Pass `psk = b"\x00" * 31` (one byte short) | Raises `HandshakeVerifyError("DRONE_PSK must be exactly 32 bytes")` before any KDF invocation |
| 4.6 | `derive_aead_ratchet()` must use HKDFExpand ONLY — no HKDF-Extract allowed | `HKDFExpand(algorithm=hashes.SHA256(), length=32, info=label).derive(base_key)` | Profile the call; verify no `HKDF.derive()` or `HKDF(salt=...)` is invoked | `from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand` only — NOT `HKDF`; HKDF.derive = 0 calls |
| 4.7 | Ratchet info MUST be direction-differentiated, session-bound | d2g info: `b"pq-drone-gcs:ratchet|d2g|" + session_id + b"|" + new_aead_id.encode()` | Pass same session_id and new_aead_id for both d2g and g2d (collapse the labels) | `assert new_k_d2g != new_k_g2d` for any non-degenerate inputs (direction tags guarantee this) |
| 4.8 | Ratchet output keys must differ from base keys | `new_k_d2g != base_key_d2g` | Pass `base_key_d2g = os.urandom(32)` | Expansion with non-trivial info guarantees `new_k != base_key` for any PRF-secure HKDF |
| 4.9 | `is_aead_shift` detection based on `key_handshake_id` equality, NOT aead_token strings | `curr_khs = negotiation_profiles_for_suite(curr_suite).get("key_handshake_id"); new_khs = ...` | Change `aead_token` but keep `key_handshake_id` the same → must trigger ratchet | `is_aead_shift = True` iff `curr_khs == new_khs` (not `curr_aead == new_aead`) |
| 4.10 | No liboqs object MUST be created during AEAD-only ratchet path | Audit `is_aead_shift = True` branch: `derive_aead_ratchet()` must have zero `KeyEncapsulation(...)` or `Signature(...)` calls | Add `KeyEncapsulation` call inside ratchet path; verify test catches it | `mock.patch("oqs.KeyEncapsulation")` usage count == 0 after `is_aead_shift=True` code path |
| 4.11 | `base_k_d2g` must be read from `active_context` under lock, not from a stale closure | `base_k_d2g = active_context.get("base_k_d2g")` inside `with context_lock:` block | Trigger concurrent rekey; check that ratchet uses updated base key, not the original | No test should observe `new_k_d2g == previously_ratcheted_old_key` when base changed |

---

## SECURITY INVARIANTS — All Phases

| # | REQUIREMENT | EXACT FUNCTION/API | NEGATIVE TEST | INVARIANT/LOG/ASSERTION |
|---|---|---|---|---|
| S.1 | Replay check BEFORE AEAD verification; window commit AFTER | `Receiver._check_replay(seq)` → then decrypt → then `Receiver._commit_replay(seq)` | Send seq=5000 then seq=1 on same epoch/key | Large seq causes window shift; seq=1 then rejected as "too old" — NOT as auth failure |
| S.2 | AEAD auth failure MUST NOT advance replay window | `_check_replay()` called before `self._cipher.decrypt()` — window commit only in `_commit_replay()` after successful decrypt | Forge a ciphertext with valid header but corrupt tag; replay same seq | First attempt: `AeadAuthError` raised, window NOT advanced. Re-send same seq with correct tag: accepted. |
| S.3 | Key confirmation via HMAC-SHA256 BEFORE accepting session | `_build_key_confirmation_tag(confirm_key, label, hello_wire, kem_ct)` — called before completing handshake | Send wrong key_confirmation_tag on handshake | `HandshakeVerifyError` raised; session ID never assigned; no key material used for data plane |
| S.4 | Session ID generated with `os.urandom(_SESSION_ID_LEN)` — never fixed/predictable | `session_id = os.urandom(_SESSION_ID_LEN)` where `_SESSION_ID_LEN = 16` | Mock `os.urandom` to return zeros; assert any security-critical path rejects it | Two consecutive handshakes produce `session_id_A != session_id_B` with overwhelming probability; log them as `session_id_hex` |
| S.5 | Wire message size guard prevents amplification attacks | `_MAX_HANDSHAKE_MSG_BYTES = 2 * 1024 * 1024`: `if kem_pub_len > _MAX_HANDSHAKE_MSG_BYTES: raise HandshakeFormatError` | Send server hello with `kem_pub_len = 0x7FFFFFFF` | `HandshakeFormatError("malformed server hello: invalid kem_pub length")` — connection closed |
| S.6 | `_zero_mutable_buffer` applied to all bytearray secrets after use | `_secure_zero(buf)` iterates and zeros each byte; called on intermediate key material after derivation | Inspect object memory after `_secure_zero`; assert all bytes are 0x00 | `all(b == 0 for b in zeroed_buf)` passes immediately after call |
| S.7 | Rekey timeout / guard prevents rapid-fire rekying | `ControlState.last_rekey_ms` checked by `safe_guard()` before accepting new PREPARE | Send two PREPARE messages within 100ms | Second PREPARE rejected via `safe_guard()` returning False; note logged "rekey too soon" |
| S.8 | Retired AEAD tokens rejected at configuration load time | `_canonicalize_aead_token("aes128gcm")` → `ValueError("AEAD token 'aes128gcm' is retired: ...")` | Configure `SUITE_AEAD_TOKEN = "aes128gcm"` in config | `ValueError` raised at `Sender.__post_init__` / first `Sender` construction — before any encryption |
| S.9 | AEAD token must be in validated set at sender/receiver construction | `_canonicalize_aead_token(token)` checks against `_SUPPORTED_AEAD_TOKENS = {"aesgcm","chacha20poly1305","ascon128","ascon128a","aegis256"}` | Pass `"aes-256-gcm"` (wrong format) or `"null"` | `ValueError("unknown AEAD token: aes-256-gcm")` at construction |
| S.10 | Epoch overflow guard — epoch 255 cannot bump | `Sender.bump_epoch()`: `if self.epoch == 255: raise AeadError(...)` | Call `bump_epoch()` on a Sender with `epoch=255` | `AeadError` raised; session must be terminated and rekeyed with epoch=0 |
| S.11 | Sequence number 64-bit range checked at Sender construction | `Sender.__post_init__`: `if self._seq < 0: raise ValueError` | Pass `_seq = -1` | `ValueError("_seq must be non-negative int")` |
| S.12 | `destroy()` sentinel check in every encrypt/decrypt call | `if self._seq < 0 or self._cipher is None: raise AeadError("sender destroyed")` | Call `destroy()` then `encrypt(b"test")` | `AeadError("sender destroyed: encrypt() called after destroy()")` — never a silent success |
| S.13 | Handshake wire format trailing-bytes guard | `_parse_server_hello_wire`: `if offset != len(wire): raise HandshakeFormatError("trailing bytes")` | Append 1 extra byte to a valid server hello wire | `HandshakeFormatError("malformed server hello: trailing bytes present")` |
| S.14 | `MAX_WIRE_LEN = 65536` guard on all received frames | `if len(wire) > MAX_WIRE_LEN: drop` | Send a 100KB UDP payload | Frame silently dropped (no exception) OR rejected with `AeadError("wire too long")` — never passed to decrypt |

---

## HKDF / KDF Multi-Source Cross-Checks

| # | REQUIREMENT | RFC/NIST SOURCE | OPENSSL CONFIRMATION | CODEBASE MAPPING |
|---|---|---|---|---|
| H.1 | Full HKDF = Extract (IKM → PRK) then Expand (PRK + info → OKM) — NEVER use Extract output directly as next Extract IKM | RFC 5869 §2; RFC 8446 §E.1.1 explicitly warns against this | `EVP_KDF_fetch(NULL,"HKDF",NULL)` with `OSSL_KDF_PARAM_MODE="EXTRACT_AND_EXPAND"` (default) | `derive_transport_material()` uses `HKDF(...)` (wraps both) — ✓ |
| H.2 | HKDF info ≤ 1024 bytes hard limit | — | OpenSSL EVP_KDF-HKDF: `OSSL_KDF_PARAM_INFO` ≤ 1024 bytes; exceeding returns error | `info = b"pq-drone-gcs:kdf:v2|" + ...` — currently ~50 bytes — ✓ with guard to add |
| H.3 | KDF input key material ≥ 112 bits (14 bytes) for FIPS compliance | NIST SP 800-132 | OpenSSL EVP_KDF-HKDF FIPS: `OSSL_KDF_PARAM_FIPS_KEY_CHECK` — key must be ≥ 112 bits | `shared_secret` from KEM is 32 bytes (256 bits) — ✓ |
| H.4 | HKDF-Expand-Label for ratchets: `"tls13 " prefix + label`; context-field = Transcript-Hash | RFC 8446 §7.1 normative definition; `HkdfLabel.label = "tls13 " + Label` | `EVP_KDF_fetch(NULL,"TLS13-KDF",NULL)` + `OSSL_KDF_PARAM_PREFIX="tls13 "` (no NUL) | `derive_aead_ratchet()` uses project-specific info, NOT TLS13-KDF — **by design**; use separate label namespace |
| H.5 | TLS13-KDF ALL params must be set in single `EVP_KDF_CTX_set_params()` call — no piecemeal | — | OpenSSL EVP_KDF-TLS13_KDF NOTES section: all parameters required atomically | N/A (project uses `cryptography` library, not OpenSSL C API directly) — note for future OpenSSL EVP migration |
| H.6 | TLS13-KDF: only EXTRACT_ONLY and EXPAND_ONLY modes; NO EXTRACT_AND_EXPAND | — | OpenSSL EVP_KDF-TLS13_KDF: returns error for EXTRACT_AND_EXPAND mode | N/A — but if TLS13-KDF is adopted, this constraint must be documented |
| H.7 | Key update label for TLS 1.3 = `"traffic upd"`; for QUIC = `"quic ku"` | RFC 8446 §7.2; RFC 9001 §6.1 | — | Current ratchet uses `"pq-drone-gcs:ratchet|d2g|..."` (domain-separated from TLS/QUIC) — ✓ |
| H.8 | QUIC header-protection key (`"quic hp"`) must NEVER change during key update | RFC 9001 §6.1 explicit: "header protection key is not updated" | — | N/A for current codebase (not QUIC); note for future QUIC transport layer |
| H.9 | Secrets must be erased after all derived values computed | RFC 8446 §7.1: "Implementations SHOULD erase secrets after use" | — | `_secure_zero(buf)` exists — must be called on `okm` bytearray after slice-copy |

---

## ML-KEM Readiness (OpenSSL 3.5+ native PQ path)

| # | REQUIREMENT | EXACT API | NEGATIVE TEST | INVARIANT |
|---|---|---|---|---|
| M.1 | ML-KEM requires OpenSSL ≥ 3.5 — must gate with version check | `import ssl; ssl.OPENSSL_VERSION_INFO >= (3, 5, 0)` or `openssl version -v` | Run on OpenSSL 3.4 → EVP_KEM-ML-KEM fetch returns NULL | `EVP_KDF_fetch` for ML-KEM returns NULL with `ERR_get_error()` → log "ML-KEM requires OpenSSL 3.5+" |
| M.2 | ML-KEM key generation via EVP_PKEY_Q_keygen | `EVP_PKEY_Q_keygen(NULL, NULL, "ML-KEM-768")` → `EVP_PKEY*` | Request `"ML-KEM-512"` and check private key size = 1632 bytes | dk (decapsulation key) size: 1632 (512), 2400 (768), 3168 (1024) bytes (FIPS 203) |
| M.3 | ML-KEM encapsulation returns 32-byte shared secret for ALL variants | `EVP_PKEY_encapsulate_init(ctx, NULL); EVP_PKEY_encapsulate(ctx, ct, &ct_len, ss, &ss_len)` | Verify `ss_len == 32` for ML-KEM-512, -768, -1024 | Shared secret is always 32 bytes regardless of security level (FIPS 203 §6.2) |
| M.4 | `OSSL_KEM_PARAM_IKME` (test-only determinism) MUST be banned in production | Audit for any non-test usage of `OSSL_KEM_PARAM_IKME` | Add a `OSSL_KEM_PARAM_IKME` call outside a `#TEST_ONLY` guarded block | CI lint rule: `grep -rn "OSSL_KEM_PARAM_IKME" core/ sscheduler/` returns zero hits |
| M.5 | PCT (pairwise consistency test) runs automatically on dk import — trust it | `EVP_PKEY_fromdata()` with `OSSL_PKEY_PARAM_PRIV_KEY` triggers PCT per FIPS 203 | Import a deliberately corrupted dk (flip one byte) | `EVP_PKEY_fromdata()` returns <= 0; `ERR_get_error()` → PCT failure code |
| M.6 | ML-KEM seed format = 64-byte `(d||z)` concatenation — not an encoded key | Key seed via `OSSL_PKEY_PARAM_ML_KEM_SEED` = `bytes[64]` (FIPS 203 Algorithm 13) | Pass 32-byte seed instead of 64 | `EVP_PKEY_fromdata()` fails; `EVP_PKEY_CTX_get_params()` would show correct seed length |

---

## REKEY_SEQ_THRESHOLD — Critical Configuration Finding

### NIST SP 800-38D §B.1 AES-GCM Limits
- **Max invocations per key (96-bit nonce)**: 2^32 ≈ 4.3 billion  
- **Max plaintext bytes per invocation**: 2^36 bytes ≈ 64 GiB

### RFC 8446 §5.5 TLS 1.3 Conservative Limit
- **AES-GCM**: ≤ 2^24.5 ≈ 24 million records per connection key  
- **ChaCha20-Poly1305**: limited by 64-bit sequence number exhaustion (effectively 2^64)

### Current Code vs. Required

```python
# core/aead.py line 338 (CURRENT — DANGEROUS DEFAULT)
threshold = int(CONFIG.get("REKEY_SEQ_THRESHOLD", 1 << 63))  # 9.2 × 10^18 — effectively never triggers

# For AES-256-GCM PRODUCTION — REQUIRED OVERRIDE
REKEY_SEQ_THRESHOLD = 1 << 23   # 8.4M packets — TLS 1.3 conservative (RFC 8446 §5.5)
# OR for permissive but NIST-compliant:
REKEY_SEQ_THRESHOLD = 1 << 32   # 4.3B packets — NIST SP 800-38D §B.1 hard limit

# For ChaCha20-Poly1305 (no practical limit):
REKEY_SEQ_THRESHOLD = 1 << 63   # current default OK for ChaCha20-Poly1305
```

### Validation Test
```python
# Negative test: verify threshold fires before NIST limit
with patch.dict(CONFIG, {"REKEY_SEQ_THRESHOLD": 4_294_967_296 + 1}):
    sender = Sender(..., aead_token="aesgcm")
    sender._seq = 4_294_967_296  # 2^32
    with pytest.raises(SequenceOverflow):
        sender.encrypt(b"test")
```

**Invariant**: `SequenceOverflow` must be raised BEFORE `seq` reaches 2^32 for `aesgcm` token.  
**Sources**: NIST SP 800-38D Table 1 + Appendix B; RFC 8446 §5.5; AES-GCM security proofs.

---

## Verification Commands Per Phase

```bash
# Phase 0: compile gate
python -m py_compile core/suites.py core/policy_engine.py core/control_tcp.py \
    core/async_proxy.py core/handshake.py core/aead.py \
    sscheduler/policy.py sscheduler/benchmark_policy.py

# Phase 1: no PQC in control_tcp
grep -n "KeyEncapsulation\|oqs\|HKDF\|hkdf\|HandshakeError" core/control_tcp.py | grep -v "import\|#"

# Phase 2: check ControlState sub-state sync
python -c "
from core.policy_engine import create_control_state
s = create_control_state('gcs', 'kyber768_aesgcm')
assert s.handshake.active_profile == s.cipher.active_profile == s.current_suite
assert s.coordinator_role == 'gcs'
print('Phase 1 state split: OK')
"

# Phase 4: ratchet produces different keys for different directions
python -c "
import os
from core.handshake import derive_aead_ratchet
k1 = os.urandom(32); k2 = os.urandom(32); sid = os.urandom(16)
nk1, nk2 = derive_aead_ratchet(k1, k2, sid, 'aesgcm')
assert nk1 != nk2, 'd2g == g2d: direction tag broken'
assert nk1 != k1, 'ratchet did not change d2g key'
assert nk2 != k2, 'ratchet did not change g2d key'
print('Phase 4 ratchet: OK')
"

# Security: REKEY_SEQ_THRESHOLD for aesgcm must be <= 2^32
python -c "
from core.config import CONFIG
from core.aead import Sender, AeadIds
import os
token = CONFIG.get('SUITE_AEAD_TOKEN', 'aesgcm')
threshold = int(CONFIG.get('REKEY_SEQ_THRESHOLD', 1 << 63))
if token == 'aesgcm' and threshold > (1 << 32):
    print(f'WARNING: REKEY_SEQ_THRESHOLD={threshold} exceeds NIST SP 800-38D 2^32 limit for AES-GCM')
    print('Set REKEY_SEQ_THRESHOLD=4294967296 in config for AES-GCM compliance')
else:
    print(f'REKEY_SEQ_THRESHOLD={threshold}: OK for {token}')
"
```

---

## Commit Sequence (per prompt format)

```
feat(core): split control state into handshake and cipher state with compatibility facade
feat(control): enforce OOB negotiate pipeline and lightweight tcp handlers  
feat(proxy): add soft rekey transition window for telemetry continuity
feat(kdf): add hkdf ratchet path for aead-only shifts
chore(core): finalize migration notes and verification report
```

---

*Checklist version: 1.0 — Multi-source confirmed from RFC 5869, RFC 8446 §7.1-7.2, RFC 9001 §5-6,
NIST SP 800-38D, OpenSSL EVP_KDF-HKDF, EVP_KDF-TLS13_KDF, EVP_KEM-ML-KEM, EVP_PKEY-ML-KEM,
and codebase reads of core/ modules on 2025-07-04.*
