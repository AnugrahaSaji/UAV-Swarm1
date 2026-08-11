# Phase 2 Core Iteration Journal
## Core-only Implementation, Observations, and Validation

Date: 2026-03-14  
Repository: `secure-tunnel`  
Branch: `main`  
Scope: `core/` only (no scheduler policy implementation work in this document)

---

## 1) Mission and Boundary Conditions

This Phase 2 journal records the implementation and validation state after the staged core refactor and hardening passes that followed Phase 1 benchmark analysis.

Hard boundaries respected:

- Only `core/` behavior and `tests/test_core_quality.py` are in scope.
- Device-agnostic logic only (no Pi4/Pi5-only assumptions introduced in core control/data path).
- No protocol claims are made without code evidence from current repository state.

---

## 2) Evidence Base Used for This Journal

### 2.1 Git timeline (core-relevant range)

- `46f7d48` `chore(core): baseline lock compile snapshot and risk ledger`
- `28ab3e8` `feat(core): split control state into handshake and cipher state with compatibility facade`
- `84c41ff` `feat(control): enforce OOB negotiate pipeline and lightweight tcp handlers`
- `03d53cc` `feat(proxy): add soft rekey transition window for telemetry continuity`
- `c6c86f0` `feat(kdf): add hkdf ratchet path for aead-only shifts`
- `1fecb1d` `chore(core): finalize migration notes and verification report`
- `03430dc` `feat(core): prune suites by runtime kem/sig support`
- `3d2bdb7` `feat(core): add crypto profile negotiation with explicit aead intent`
- `f754756` `feat(core): add control timeout recovery and deterministic cb failure path`
- `a7eeca1` `refactor(core): enforce strict kem-ds suite IDs and drop legacy aead aliases`
- `d68a17c` `feat(core): enforce 8-profile AEAD matrix across L1/L3/L5`

### 2.2 Files reviewed for this iteration report

- `core/policy_engine.py`
- `core/control_tcp.py`
- `core/async_proxy.py`
- `core/handshake.py`
- `core/aead.py`
- `core/suites.py`
- `core/run_proxy.py`
- `core/config.py`
- `core/refactor_verification_log.md`
- `core/refactor_migration_notes.md`
- `tests/test_core_quality.py`

### 2.3 Runtime commands executed for current-state confirmation

- `python -m py_compile core/suites.py core/policy_engine.py core/control_tcp.py core/async_proxy.py core/handshake.py core/aead.py sscheduler/policy.py sscheduler/benchmark_policy.py`
  - Outcome: pass
- `python tests/test_core_quality.py`
  - Outcome: `42 passed, 0 failed, 0 skipped`
- `python -` probe:
  - `len(list_suites()) == 24`
  - `aead_profiles_by_nist_level() == {'L1': ('aesgcm','aesccm','ascon128a'), 'L3': ('aesgcm','aesccm'), 'L5': ('aesgcm','aesccm','chacha20poly1305')}`
  - `available_aead_tokens() == ('aesgcm','aesccm','chacha20poly1305','ascon128a')` in current runtime

---

## 3) Core System Wiring (Current Mental Model)

### 3.1 Control plane

Control intent ingress has two sources:

1. In-band encrypted control packets (`type=0x02` payload path) processed in `core/async_proxy.py` through `handle_control(...)` in `core/policy_engine.py`.
2. Optional out-of-band TCP JSON control in `core/control_tcp.py`, which validates and queues intent only via `request_prepare(...)`.

Coordinator semantics:

- Coordinator role comes from config (`CONTROL_COORDINATOR_ROLE`, normalized to `gcs|drone`).
- Only coordinator can drive prepare/commit progression.
- Non-coordinator processes prepare/commit/status messages and launches rekey worker only when state machine says so.

Control state model:

- `ControlState` is the compatibility facade.
- Internal split:
  - `HandshakeState` tracks key-handshake profile and epoch.
  - `CipherState` tracks active AEAD profile and epoch.
- Facade sync logic in `__setattr__` keeps legacy fields (`current_suite`, `current_aead`, `epoch`) coherent with split states.

### 3.2 Data plane

Data path in `core/async_proxy.py`:

- Plaintext ingress UDP -> optional packet-type processing -> `Sender.encrypt(...)` -> encrypted UDP peer.
- Encrypted ingress UDP -> source validation -> `Receiver.decrypt(...)` -> plaintext egress UDP.

AEAD framing in `core/aead.py`:

- Header includes version, kem/sig IDs, session_id, seq, epoch.
- AAD binding includes header.
- Nonce is deterministic from `(epoch, seq)`, not transmitted on wire.
- Replay protection uses check-then-commit window update (commit only after auth success).

### 3.3 Rekey path

Rekey authority remains in `core/async_proxy.py` worker thread:

- Control packet or TCP intent reaches policy state machine.
- Worker selects path:
  - Full PQC handshake if key-handshake profile changes (or AEAD-only conditions not met).
  - HKDF AEAD-only ratchet when key-handshake ID is unchanged and AEAD token changes.
- New sender/receiver contexts are built and swapped atomically under `context_lock`.
- Soft transition keeps `prev_receiver` active for bounded grace window to avoid telemetry blackout.

---

## 4) Implementation Progress by Pass (Detailed)

## 4.1 Baseline lock (`46f7d48`)

What was done:

- Baseline compile gate captured.
- Initial risk ledger created (`core/refactor_verification_log.md`).

Why it matters:

- Established a deterministic starting point before semantic edits.

---

## 4.2 State engine split/facade tightening (`28ab3e8`)

Files:

- `core/policy_engine.py`

What changed:

- Existing split model formalized through compatibility facade behavior.
- `pending_suite` facade semantics tightened.
- Synchronization logic ensures writes to legacy fields update split state.

Operational effect:

- Existing call sites using monolithic state model continue to work.
- Internal state representation is clearer for handshake-vs-cipher transitions.

---

## 4.3 OOB control-plane hardening (`84c41ff`)

Files:

- `core/control_tcp.py`

What changed:

- TCP handler remains lightweight and non-crypto.
- Added strict bounded input parsing:
  - max list items
  - max token length
- Added explicit authorization + coordinator checks + per-peer rekey rate limiting.
- Added negotiated profile resolver using capability offers/preferences (`suite + aead` selection path).

Operational effect:

- Control TCP endpoint now behaves as a secure intent gateway, not a crypto execution path.
- Heavy PQC/rekey work remains in async proxy worker.

---

## 4.4 Soft-transition data plane (`03d53cc`)

Files:

- `core/async_proxy.py`

What changed:

- Added transition helpers:
  - `_soft_transition_active(...)`
  - `_decrypt_with_transition(...)`
  - peer-matching helper split
- During grace window, previous receiver + previous peer can still be accepted.
- Deferred-destroy queue keeps old receiver alive until transition deadline.

Operational effect:

- Reduces in-flight packet loss during rekey cutover.
- Preserves replay/session checks by whichever receiver successfully decrypts.

---

## 4.5 HKDF AEAD-only ratchet (`c6c86f0`)

Files:

- `core/handshake.py`
- `core/aead.py`
- `core/async_proxy.py`

What changed:

- Introduced `derive_aead_ratchet(...)` path with AEAD-key-length-aware derivation.
- Added required key-length selector in `core/aead.py`.
- Fixed explicit AEAD token application in sender/receiver rebuild path.

Operational effect:

- AEAD-only transitions avoid full liboqs handshake path when key-handshake profile is unchanged.
- Target AEAD token is now deterministically applied during transition object construction.

---

## 4.6 Runtime suite pruning (`03430dc`)

Files:

- `core/suites.py`
- `tests/test_core_quality.py`

What changed:

- Added runtime prune path that removes suites with unavailable runtime KEM/SIG support.
- Keeps static registry as canonical definition while allowing runtime-safe usable subset.

Operational effect:

- Prevents advertising/trying obviously unsupported suites when runtime capability probing succeeds.

Important caveat:

- If both KEM and SIG probing fail, static registry is preserved to avoid startup collapse.

---

## 4.7 Negotiated crypto profile (`3d2bdb7`)

Files:

- `core/suites.py`
- `core/control_tcp.py`
- `core/policy_engine.py`
- `core/async_proxy.py`

What changed:

- Added split crypto profile negotiation output:
  - `suite_id` (key-handshake profile)
  - `aead_token` / `data_aead_id` (data-plane profile)
- TCP control can negotiate using offers/preferences rather than only fixed suite input.

Operational effect:

- Rekey intent now carries explicit AEAD selection path in addition to suite.

---

## 4.8 Timeout recovery + deterministic failure path (`f754756`)

Files:

- `core/policy_engine.py`
- `core/async_proxy.py`
- `core/config.py`

What changed:

- Added stale-state timeout recovery for `NEGOTIATING`/`SWAPPING`.
- Added clearer failure accounting and deterministic status payload on timeout.

Operational effect:

- Control plane has bounded recovery instead of indefinite stale negotiation state.

---

## 4.9 Strict `kem-ds` suite IDs only (`a7eeca1`)

Files:

- `core/suites.py`
- `core/metrics_schema.py`
- `core/metrics_aggregator.py`
- `core/robust_logger.py`
- `tests/test_core_quality.py`

What changed:

- Enforced suite identity model: `cs-{kem}-{sig}` only.
- Removed legacy AEAD-embedded suite ID acceptance (`cs-{kem}-{aead}-{sig}` style).
- Updated tests/metrics paths to reflect split key-handshake/data-aead model.

Operational effect:

- Handshake transcript identity and suite namespace are simplified and consistent with the split negotiation model.

---

## 4.10 8 AEAD profiles across 3 NIST levels (`d68a17c`)

Files:

- `core/suites.py`
- `core/aead.py`
- `tests/test_core_quality.py`

What changed:

- Added AES-CCM support to runtime AEAD primitive wiring.
- Added level-aware AEAD profile matrix:
  - `L1`: `aesgcm`, `aesccm`, `ascon128a`
  - `L3`: `aesgcm`, `aesccm`
  - `L5`: `aesgcm`, `aesccm`, `chacha20poly1305`
- Added API: `aead_profiles_by_nist_level(runtime_only=False|True)`.
- Updated profile selection so AEAD selection is constrained by selected suite NIST level.
- Added tests:
  - L3 policy enforcement test (Ascon not selected at L3).
  - Explicit matrix integrity test (`3 + 2 + 3 = 8 profiles`).

Operational effect:

- AEAD profile choice is now policy-driven per NIST level, not just availability/preference driven.

---

## 5) Current Crypto Profile Model (As Implemented)

## 5.1 Suite identity model

Canonical suite identifier:

- `cs-{kem}-{sig}`

No AEAD token in suite ID.

Meaning:

- Key-handshake identity is decoupled from data-plane AEAD profile.

## 5.2 Canonical suite cardinality

Current canonical registry count is 24 suites (level-aligned combinations):

- L1: 3 KEM x 3 SIG = 9
- L3: 3 KEM x 2 SIG = 6
- L5: 3 KEM x 3 SIG = 9

Total: 24

## 5.3 AEAD policy cardinality

The "8 AEAD profiles" are policy entries across levels, not 8 distinct AEAD algorithms:

- L1 has 3 allowed AEAD tokens
- L3 has 2 allowed AEAD tokens
- L5 has 3 allowed AEAD tokens

Total policy entries: 8

Distinct AEAD tokens used in this matrix: 4 (`aesgcm`, `aesccm`, `ascon128a`, `chacha20poly1305`).

---

## 6) Key Lifecycle and Isolation Analysis (Direct answer to overlap question)

This section answers:

> "we have 24 suites and all 8 AEADs, do we have separate individual keys with no overlap?"

Short answer:

- For transport/session keys: yes, keys are session-derived and direction-separated.
- For suite identity keys (signature keys): separation is supported, but uniqueness is operator-provisioned, not forced by protocol code.
- "8 AEADs" should be read as 8 level-policy entries, not 8 independent AEAD algorithms.

Detailed breakdown:

### 6.1 Signature identity keys (long-term)

- Loaded from disk/inputs via `core/run_proxy.py`.
- Per-suite loaders exist:
  - `load_gcs_secret` from `secrets/matrix/<suite_id>/gcs_signing.key`
  - `load_gcs_public` from `secrets/matrix/<suite_id>/gcs_signing.pub`
- This enables separate identity keys per suite.

Important:

- Core supports per-suite separation, but does not cryptographically enforce uniqueness across files.
- If same key material is reused across multiple suite files, overlap exists by operator choice.

### 6.2 KEM ephemeral keys (per handshake)

- Generated fresh in handshake (`build_server_hello` -> `KeyEncapsulation(...).generate_keypair()`).
- Not pre-generated "24 static KEM keys" in registry.

### 6.3 Session transport keys (data plane)

- Derived in `derive_transport_material(...)` from:
  - shared secret
  - session_id
  - challenge
  - kem_name
  - sig_name
  - epoch
  - PSK digest influence
- Output is directional:
  - `key_d2g`
  - `key_g2d`
- Directional split means send/recv keys are not reused as one shared key.

### 6.4 AEAD-only shift keys

- Derived by `derive_aead_ratchet(...)` from:
  - previous directional base key
  - session_id
  - target AEAD token
  - epoch
- Key length depends on target AEAD requirements.
- This avoids liboqs calls for AEAD-only transitions.

### 6.5 Overlap statement (practical)

No intentional overlap in active transport key assignment:

- `d2g` and `g2d` are separate.
- New handshake sessions derive fresh keys.
- AEAD shift uses explicit derivation context.

Residual non-absolute points:

- Absolute "impossible overlap" cannot be claimed mathematically for any HKDF-based system.
- Operationally, overlap risk comes mainly from key provisioning reuse (e.g., same signing key file reused across suites), not from transport derivation design.

---

## 7) Security Invariants Status (Current Core)

Preserved in current implementation:

- Peer validation constraints remain.
- Coordinator restrictions remain.
- Replay checks remain check-then-commit.
- Session and epoch checks remain enforced on decrypt.
- Rekey timeout/liveness and overlap guards are present.
- TCP control handler remains non-crypto execution path.

Implemented hardening worth noting:

- Control parser bounds.
- Rekey rate limiting.
- Circuit-breaker hooks.
- Soft transition continuity and bounded old-context acceptance.
- Deferred key-context destroy with best-effort zeroization.

Explicit limitation recorded in code comments:

- Python-level zeroization cannot guarantee wiping C-heap key copies held by crypto backend objects.

---

## 8) Validation Summary (Current Snapshot)

Compile:

- Core compile gate passes for targeted modules.

Tests:

- `tests/test_core_quality.py` passes (`42/42` in current run).

Policy checks proven by tests:

- Legacy AEAD-embedded suite IDs rejected.
- L3 AEAD policy enforcement verified.
- 8-profile AEAD matrix integrity verified.
- Replay/session/epoch guard behavior validated.

---

## 9) Remaining Gaps / Non-finalized Areas

1. Full matrix runtime execution is environment-dependent:
- Canonical registry has 24 suites.
- Runtime usable subset depends on available oqs KEM/SIG algorithms and AEAD backend support.

2. Per-suite signing-key uniqueness policy is operational, not enforced:
- Code can load per-suite keys, but does not enforce uniqueness constraints across files.

3. AEAD token support in `core/aead.py` vs policy registry in `core/suites.py` is intentionally narrower in negotiation:
- Data plane primitive module supports additional tokens (`ascon128`, `aegis256`) beyond current level-policy matrix.
- Negotiation matrix currently uses the 4-token policy set described above.

4. Full localhost exhaustive matrix run (`24 suites x 8 profile entries`) is not executed in this document:
- This report captures implementation correctness + unit/integration guardrails, not final exhaustive benchmark campaign output.

---

## 10) Phase 2 Conclusion

Core foundation is significantly stronger than Phase 1 baseline:

- Control-plane semantics are cleaner and bounded.
- Rekey transition continuity is materially improved.
- AEAD-only agility is explicit and correctly keyed.
- Suite identity is now strict `kem-ds`.
- NIST-level AEAD policy matrix is implemented and tested (8 profile entries across L1/L3/L5).

For your specific key-isolation question:

- The architecture supports clean per-suite/per-session key separation.
- Transport key overlap is not intentionally present in the current design.
- Identity-key overlap can still occur if the same key files are reused across suites; enforce unique material in `secrets/matrix/<suite_id>/...` to guarantee operational separation.

