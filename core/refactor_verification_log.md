# Core Refactor Verification Log

## Phase 0 - Baseline Lock

### Scope

- Core-only baseline capture before semantic edits.
- Device-agnostic snapshot only. No host-specific assumptions added.

### Git Snapshot

- Branch: `main`
- Pre-existing untracked file outside this sprint scope:
  - `sscheduler/schedulerpolicyv2.md`

### Compile Gate

Command:

```powershell
python -m py_compile core/suites.py core/policy_engine.py core/control_tcp.py core/async_proxy.py core/handshake.py core/aead.py sscheduler/policy.py sscheduler/benchmark_policy.py
```

Outcome:

- Passed with no compile errors.

### Behavior Snapshot

Validated current control-plane behavior with targeted Python smoke checks:

- `request_prepare()` transitions leader state to `NEGOTIATING`.
- follower `handle_control(prepare_rekey)` returns `prepare_ok`.
- leader `handle_control(prepare_ok)` emits `commit_rekey` and enters `SWAPPING`.
- `record_rekey_result(..., success=True)` updates:
  - `current_suite`
  - `handshake.active_profile`
  - `cipher.active_profile`
  - `last_rekey_suite`
- epoch replay and rollback rejection remains active for repeated or lower epochs.

### Phase 0 Risk Ledger

Low:

- `core/policy_engine.py` already contains split `HandshakeState` and `CipherState`, reducing Phase 1 churn.

Medium:

- `ControlState` currently exposes split state plus legacy top-level fields, but synchronization is manual.
- External writes to top-level facade fields could drift from nested split state if future callers mutate them directly.

High:

- None observed in compile baseline or targeted control-plane smoke checks.

### Exit Decision

- Go for Phase 1.
- Reason: compile baseline is clean and the current split-state behavior is stable enough for a compatibility-facade tightening pass.

## Phase 1 - State Engine Facade Tightening

### Files Changed

- `core/policy_engine.py`
- `core/refactor_verification_log.md`

### Change Summary

- Kept the existing split `HandshakeState` and `CipherState` design.
- Tightened `ControlState` into a self-synchronizing compatibility facade.
- Added synchronized facade behavior for:
  - `current_suite`
  - `epoch`
  - `pending_suite`
- Centralized pending-suite synchronization in `request_prepare()`, `record_rekey_result()`, and `handle_control()`.

### Invariants Preserved

- `request_prepare()` API unchanged.
- `record_rekey_result()` API unchanged.
- epoch monotonicity and rollback rejection preserved.
- coordinator-role behavior preserved.
- no peer-validation or allowlist logic moved out of existing modules.
- no rekey execution authority moved out of runtime worker paths.

### Verification

Compile gate:

```powershell
python -m py_compile core/suites.py core/policy_engine.py core/control_tcp.py core/async_proxy.py core/handshake.py core/aead.py sscheduler/policy.py sscheduler/benchmark_policy.py
```

Outcome:

- Passed.

Targeted behavior checks:

- direct facade writes to `current_suite` now synchronize:
  - `handshake.active_profile`
  - `cipher.active_profile`
- direct facade writes to `epoch` now synchronize:
  - `handshake.epoch`
  - `cipher.epoch`
- `request_prepare()` still:
  - increments epoch
  - enters `NEGOTIATING`
  - preserves pending-suite tracking
- follower `handle_control(prepare_rekey)` still returns `prepare_ok`.
- leader `handle_control(prepare_ok)` still emits `commit_rekey`.
- `record_rekey_result(..., success=True)` still restores `RUNNING` and clears pending-suite state.
- replay and rollback protection still reject same-epoch and lower-epoch prepare messages.

### Risks Introduced

Low:

- `ControlState.__setattr__` now performs split-state synchronization, so future facade fields with the same names must avoid conflicting semantics.

Medium:

- The facade still assumes a single active rekey negotiation at a time, matching current runtime behavior.

High:

- None observed in Phase 1 verification.

### Exit Decision

- Go.
- Reason: existing callers continue to compile, control-plane smoke behavior is unchanged, and the compatibility facade is stronger than the baseline.

## Phase 2 - OOB Control-Plane Hardening

### Files Changed

- `core/control_tcp.py`
- `core/refactor_verification_log.md`

### Change Summary

- Kept `core/control_tcp.py` as a validation-and-intent layer only.
- Added bounded parsing for untrusted capability offers:
  - max item count
  - max token length
- Centralized:
  - rekey authorization
  - coordinator-only enforcement
  - per-peer rate limiting
  - direct suite resolution
  - intent queueing via `request_prepare()`
- Added explicit control-decision logging with `decision=intent_queued` or reject reasons.
- Exposed `pending_suite` in the status response for easier runtime observability.

### Invariants Preserved

- TCP handlers still do not execute PQC handshakes, KEM, signature, HKDF, or AEAD transitions.
- Rekey execution authority remains in `core.async_proxy.py`.
- peer allowlist restrictions preserved.
- rekey peer restrictions preserved.
- coordinator-only restrictions preserved.
- `request_prepare()` remains the only state-transition entry point used by TCP handlers.

### Verification

Compile gate:

```powershell
python -m py_compile core/suites.py core/policy_engine.py core/control_tcp.py core/async_proxy.py core/handshake.py core/aead.py sscheduler/policy.py sscheduler/benchmark_policy.py
```

Outcome:

- Passed.

Targeted behavior checks:

- unauthorized peer `cmd=rekey` returns `unauthorized_rekey`
- non-coordinator `cmd=rekey` returns `coordinator_only`
- valid direct `cmd=rekey`:
  - returns `{ok: true, rid, suite}`
  - enqueues `prepare_rekey` into control outbox
  - transitions control state to `NEGOTIATING`
- malformed negotiated offer with oversized token returns bounded parser error
- valid `cmd=negotiate_rekey`:
  - returns selected suite
  - enqueues `prepare_rekey`
- source audit confirms `core/control_tcp.py` still does not import or invoke handshake or AEAD runtime functions

### Risks Introduced

Low:

- Rate limiting is checked before full payload validation, so a repeated malformed request from an already-active peer may return `rekey_rate_limited` instead of the deeper validation error.

Medium:

- Status responses now expose `pending_suite`, increasing observability but also slightly increasing visible scheduler state to authorized peers.

High:

- None observed in Phase 2 verification.

### Exit Decision

- Go.
- Reason: the TCP layer remains lightweight, bounded, coordinator-safe, and strictly limited to queuing rekey intent.

## Phase 3 - Soft-Transition Data Plane

### Files Changed

- `core/async_proxy.py`
- `core/refactor_verification_log.md`

### Change Summary

- Added explicit soft-transition helpers for:
  - peer matching
  - transition-window activation
  - bounded decrypt fallback to previous receiver
- Fixed the main continuity gap:
  - previous receiver is now tried when the current receiver returns `None`
    for old-session packets during the active transition window
- Added dual-peer acceptance during the grace window:
  - packets from the previous encrypted peer endpoint can be accepted while
    the previous receiver remains active
- Added explicit transition context state:
  - `prev_receiver`
  - `prev_peer_addr`
  - `prev_receiver_deadline`
- Adjusted deferred-destroy timing:
  - old sender can be destroyed immediately at the next safe point
  - old receiver remains until the bounded grace deadline
- Added semantic logs for transition arm and expiry.

### Invariants Preserved

- replay protection remains enforced by the receiver actually used for decrypt.
- session and epoch protections remain intact.
- source-address restrictions remain active; the only widening is bounded
  acceptance of the immediately previous peer during the configured grace window.
- rekey execution path still resides in `core.async_proxy.py`.
- no handshake-lock or control-plane ownership changes were introduced.

### Verification

Compile gate:

```powershell
python -m py_compile core/suites.py core/policy_engine.py core/control_tcp.py core/async_proxy.py core/handshake.py core/aead.py sscheduler/policy.py sscheduler/benchmark_policy.py
```

Outcome:

- Passed.

Controlled local continuity checks:

- old-session packet on same peer:
  - current receiver returns `None`
  - previous receiver accepts
  - plaintext continuity preserved
- old-session packet on previous peer endpoint:
  - accepted during active grace window
  - plaintext continuity preserved
- expired grace window:
  - fallback disabled
  - packet remains rejected with `session` reason
- replay on previous receiver:
  - packet rejected
  - previous receiver reports `replay`

Helper checks:

- strict peer match behaves as before
- relaxed peer match remains IP-only
- transition window activation respects deadline state

### Risks Introduced

Low:

- During the bounded grace window, packets from the immediately previous
  encrypted peer endpoint are accepted in addition to the new endpoint.

Medium:

- Soft-transition correctness now depends on accurate cleanup of
  `prev_receiver`, `prev_peer_addr`, and `prev_receiver_deadline`, which is
  handled by the deferred-destroy safe point.

High:

- None observed in synthetic continuity verification.

### Exit Decision

- Go.
- Reason: controlled local verification shows continuity through the soft
  transition window without relaxing replay or session protections.

## Phase 4 - HKDF Ratchet for AEAD-Only Shifts

### Files Changed

- `core/aead.py`
- `core/handshake.py`
- `core/async_proxy.py`
- `core/refactor_verification_log.md`

### Change Summary

- Added explicit AEAD key-length selection in `core.aead`:
  - 32 bytes for AES-GCM, ChaCha20-Poly1305, and AEGIS-256
  - 16 bytes for Ascon variants
- Updated `derive_aead_ratchet()` to derive the correct amount of key material
  for the target AEAD instead of always deriving 32 bytes.
- Tightened the AEAD-only ratchet branch in `core.async_proxy.py`:
  - only applies when `key_handshake_id` is unchanged
  - only applies when `data_aead_id` actually changes
- Fixed a hidden token-application bug:
  - `_build_sender_receiver()` now accepts an explicit `aead_token`
  - rekey worker passes the target AEAD token directly when building new objects
  - prevents stale `cfg["SUITE_AEAD_TOKEN"]` from silently keeping the old AEAD
- Added explicit logs and metrics for AEAD-only ratchet decisions.

### Invariants Preserved

- AEAD-only shifts still avoid liboqs and full handshake execution.
- non-AEAD-only rekeys still use the existing handshake path.
- replay, session, and epoch protections remain unchanged.
- compatibility for existing `_build_sender_receiver()` call sites preserved via optional parameter defaulting to config.

### Verification

Compile gate:

```powershell
python -m py_compile core/suites.py core/policy_engine.py core/control_tcp.py core/async_proxy.py core/handshake.py core/aead.py sscheduler/policy.py sscheduler/benchmark_policy.py
```

Outcome:

- Passed.

Targeted ratchet checks:

- `derive_aead_ratchet(..., 'chacha20poly1305')` returns 32-byte keys
- `derive_aead_ratchet(..., 'ascon128')` returns 16-byte keys
- explicit target AEAD token overrides stale config token in `_build_sender_receiver()`
- ratcheted drone sender and GCS receiver successfully encrypt/decrypt with the target AEAD
- local no-liboqs smoke:
  - OQS entry points were replaced with forbidden stubs
  - `derive_aead_ratchet()` still succeeded

Source-level checks:

- AEAD-only ratchet branch now requires `curr_aead_id != new_aead_id`
- ratchet path logs `AEAD-only rekey ratchet selected`
- new sender/receiver creation now passes `aead_token=new_aead_token`

### Risks Introduced

Low:

- Ascon ratchets now derive 16-byte keys explicitly instead of deriving 32 and relying on downstream truncation.

Medium:

- The AEAD-only ratchet branch is now narrower by design; same-handshake same-AEAD rekeys fall back to the full handshake path.

High:

- None observed in targeted ratchet verification.

### Exit Decision

- Go.
- Reason: AEAD-only shifts now derive correctly-sized keys, apply the target
  AEAD deterministically, and do not depend on liboqs.

## Phase 5 - Final Hardening and Docs

### Files Changed

- `core/suites.py`
- `core/refactor_migration_notes.md`
- `core/refactor_verification_log.md`

### Change Summary

- Fixed a latent core config bug in `core.suites`:
  - `_probe_aead_support()` now uses `_CONFIG`
  - this restores `available_aead_tokens()` runtime behavior
- Added a migration note covering:
  - compatibility facade guarantees
  - TCP control semantics
  - soft-transition behavior
  - AEAD-only ratchet semantics
  - residual risks and operational guidance
- Finalized the verification report for Phases 0 through 5.

### Invariants Preserved

- No control-plane authorization or coordinator rules changed in Phase 5.
- No replay, session, or timeout behavior changed in Phase 5.
- No host- or hardware-specific assumptions were introduced.

### Verification

Compile gate:

```powershell
python -m py_compile core/suites.py core/policy_engine.py core/control_tcp.py core/async_proxy.py core/handshake.py core/aead.py sscheduler/policy.py sscheduler/benchmark_policy.py
```

Outcome:

- Passed.

Core regression gate:

```powershell
python -X utf8 tests/test_core_quality.py
```

Outcome:

- Passed: `37 passed, 0 failed`

Note:

- `pytest` is not installed in the current shell environment, so the direct Python test harness entrypoint was used instead.

Additional spot check:

```powershell
python -X utf8 -
from core.suites import available_aead_tokens
print(available_aead_tokens())
```

Outcome:

- Passed: runtime AEAD set includes `ascon128` and excludes retired legacy tokens

### Risks Introduced

Low:

- None observed in Phase 5.

Medium:

- None observed in Phase 5.

High:

- None unresolved at sprint close.

### Exit Decision

- Go.
- Reason: migration notes are in place, verification is green, and no unresolved high-severity risks remain.
