# Core Protocol Invariants

This document freezes the non-negotiable transport invariants for `core/`.

## Control Plane

- No unauthenticated downgrade of KEM, signature, or AEAD parameters.
- Rekey requests may be queued only by authorized peers and the configured coordinator role.
- TCP control admission must stay bounded: no unbounded queue growth, no unlimited idle clients, no unlimited per-IP fan-out.
- Runtime auto-selection is restricted to operationally approved profiles only.

## Data Plane

- Replay state advances only after authenticated decryption succeeds.
- Encrypted UDP source binding must not relax during soft rekey transitions.
- Previous-receiver fallback is valid only for the authenticated previous peer and only inside the grace window.
- Plaintext peer discovery may change only from an unlatch state to a concrete peer; rekey must not silently reset it.

## Registry And Policy

- `cs-{kem}-{sig}` remains the canonical suite identity. AEAD stays a runtime profile dimension.
- Registry metadata must distinguish approved operational profiles from benchmark-only and experimental profiles.
- Hidden aliases must not promote legacy or experimental primitives into the operational baseline.
- Runtime Ascon exposure, when enabled, must refer only to standardized `Ascon-AEAD128`.
- The first operational baseline is fixed to:
  - `cs-mlkem512-mldsa44`
  - `cs-mlkem768-mldsa65`
  - `cs-mlkem1024-mldsa87`
