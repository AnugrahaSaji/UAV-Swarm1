# Core Refactor Migration Notes

## Scope

This note documents the staged core refactor completed across:

- `core/policy_engine.py`
- `core/control_tcp.py`
- `core/async_proxy.py`
- `core/handshake.py`
- `core/aead.py`
- `core/suites.py`

The refactor stayed core-only and device-agnostic.

## Compatibility Surface

### Control State

- `ControlState` remains the public compatibility facade.
- Existing callers can continue to use:
  - `current_suite`
  - `epoch`
  - `request_prepare()`
  - `record_rekey_result()`
- Internally, state is now synchronized with:
  - `HandshakeState`
  - `CipherState`

### TCP Control Plane

- `core/control_tcp.py` remains the legacy OOB JSON entry point.
- It now only:
  - validates input
  - enforces peer and coordinator restrictions
  - rate-limits peers
  - resolves suite intent
  - queues `request_prepare()`
- It does not execute PQC, HKDF, or AEAD runtime work.

### Sender/Receiver Construction

- `_build_sender_receiver()` now accepts optional `aead_token=...`.
- Existing call sites remain compatible because the parameter defaults to `cfg["SUITE_AEAD_TOKEN"]`.
- New rekey code should pass the explicit target AEAD token when building transition objects.

## Protocol-Semantic Changes

### Soft Transition Window

- Rekey now supports a bounded previous-receiver grace window.
- During that window:
  - the current encrypted peer is accepted
  - the immediately previous encrypted peer may also be accepted
  - only the previous receiver may decrypt old-session packets
- Replay and session checks remain enforced by the receiver that actually decrypts the packet.

### AEAD-Only Ratchet

- AEAD-only ratchet now applies only when:
  - `key_handshake_id` is unchanged
  - `data_aead_id` changes
- Same-handshake, same-AEAD rekeys now stay on the handshake path instead of taking the AEAD-only ratchet shortcut.

### AEAD Key Lengths

- Ratcheted key material is now derived to the target AEAD's required length.
- This is explicit for:
  - AES-GCM: 32 bytes
  - ChaCha20-Poly1305: 32 bytes
  - AEGIS-256: 32 bytes
  - Ascon variants: 16 bytes

## Operational Guidance

### For new control integrations

- Treat TCP control responses as "intent queued", not "rekey executed".
- Runtime completion still happens asynchronously through the in-band worker path.

### For new scheduler integrations

- Use `status` plus `pending_suite` to observe queued transitions.
- Do not infer completion from `cmd=rekey` success alone.

### For new crypto-profile transitions

- If KEM or signature changes: use full handshake path.
- If only AEAD changes: use AEAD-only ratchet path.

## Residual Risks

- The refactor preserves the single-active-negotiation model already used by runtime control logic.
- Soft-transition correctness depends on safe-point cleanup of previous receiver state.
- Direct `pytest` execution is not available in the current shell environment; direct script execution under UTF-8 mode was used for the core-quality suite.
