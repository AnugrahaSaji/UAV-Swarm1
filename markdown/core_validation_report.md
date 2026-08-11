# Core Component Validation and Comparative Analysis Report

## 1. Executive Summary

This report provides a deep-dive architectural validation and comparative analysis of the `core/` directory in the PQC Drone-GCS Secure Proxy codebase. The implementation provides a Post-Quantum Cryptography (PQC) secured UDP proxy, incorporating a two-phase in-band control plane for key rotation. The architecture was evaluated against industry-standard cryptographic protocol designs, including **WireGuard**, **TLS 1.3**, **Signal**, and the **Noise Protocol Framework**.

The analysis confirms that the codebase correctly implements critical security invariants such as authenticated key exchange, strict AEAD framing, monotonically increasing epochs, sliding window replay protection, and memory-safe key lifecycle management (zeroization).

## 2. Architectural Comparison

### 2.1 Key Exchange and Authentication (vs. TLS 1.3 & Noise)
The PQC handshake (`core/handshake.py`) utilizes a modern Key Encapsulation Mechanism (KEM) combined with digital signatures, mirroring the **TLS 1.3** handshake structure (specifically the TLS 1.3 1-RTT handshake) and the **Noise Framework**.

*   **PQC Agility:** Like TLS 1.3's cipher suite negotiation, the implementation supports dynamic algorithm negotiation (`core/suites.py`), aligning KEMs and Signatures at identical NIST security levels (e.g., L1, L3, L5).
*   **Authentication:** The server (GCS) is authenticated via a PQC signature (e.g., ML-DSA) over the full transcript, preventing downgrade attacks. The client (Drone) is authenticated via an HMAC over the transcript using a pre-shared key (`DRONE_PSK`), combined with mutual key confirmation MACs. This hybrid approach provides robust mutual authentication.
*   **Key Derivation (HKDF):** The derivation of transport material utilizes `HKDF-SHA256` (RFC 5869), securely binding the shared secret, `DRONE_PSK`, session ID, KEM/SIG names, and a monotonic `epoch` counter. This matches the TLS 1.3 key schedule design.

### 2.2 AEAD Framing and Data Plane (vs. WireGuard)
The data plane (`core/aead.py`) heavily draws inspiration from the **WireGuard** protocol.

*   **Deterministic Nonces (IVs):** Similar to WireGuard, nonces are implicitly reconstructed from a monotonic sequence number (`seq`) and an `epoch` counter, rather than transmitted over the wire. This saves 12 bytes per packet, crucial for high-throughput drone telemetry.
*   **Replay Protection:** A sliding window bitmask (RFC 6479 pattern) is implemented in `Receiver._check_replay` and `Receiver._commit_replay`. Crucially, the window is only advanced *after* the AEAD tag is verified, preventing an attacker from forging high-sequence packets to desynchronize the window (a classic vulnerability if done pre-authentication).
*   **AEAD Primitives:** Support for AES-256-GCM, ChaCha20-Poly1305, and lightweight primitives like Ascon-128a directly aligns with modern secure transport standards.

### 2.3 State Management and Rekeying (vs. Signal & TLS 1.3 KeyUpdate)
The control plane (`core/policy_engine.py` and `core/async_proxy.py`) handles continuous rotation of key material.

*   **Split State Model:** The implementation elegantly splits state into `HandshakeState` and `CipherState`. This allows for "Symmetric Shifts" (AEAD ratcheting without a full PQC handshake), analogous to **TLS 1.3 `KeyUpdate`** or the **Signal Protocol's symmetric ratchet**.
*   **Monotonic Epochs:** The `ControlState.epoch` strictly increases. A downgrade rejection guard in `handle_control` ensures an attacker cannot force a rollback to a compromised prior state.
*   **Soft Transition Window:** To prevent telemetry drops during rekeys, `async_proxy.py` implements a dual-context accept period (retaining `prev_receiver` for 5 seconds). This is an industry-standard practice for hitless key rotation (similar to WireGuard's key overlapping).

### 2.4 Out-of-Band (OOB) Control Plane Hardening
The codebase enforces strict separation of concerns regarding cryptographic computation:
*   `core/control_tcp.py` handles external legacy JSON commands but acts strictly out-of-band. It validates commands and enqueues intents.
*   **Thread Starvation Prevention:** Heavy PQC operations (liboqs calls) are explicitly banned from the TCP handler loop and are strictly deferred to the `core/async_proxy.py` runtime worker thread. This prevents DoS attacks where an adversary floods the control port to exhaust CPU resources.

## 3. Validation of Security Invariants

The following critical security invariants were manually verified during the code audit:

1.  **Peer Validation:** Implemented strictly in `control_tcp.py` (`_is_allowed_peer`, `_is_allowed_rekey_peer`) and `async_proxy.py` (strict UDP peer IP/port matching).
2.  **Coordinator Restrictions:** The `is_coordinator` check ensures that only the designated authority (e.g., GCS) can approve rekey commits, preventing rogue endpoints from forcing rotations.
3.  **Replay/Session Protections:**
    *   The `SESSION_ID` and `EPOCH` are bound into the AEAD header and HKDF info string.
    *   `Receiver.decrypt` strictly drops packets with mismatched session IDs or epochs.
4.  **Key Material Zeroization (Forward Secrecy hygiene):**
    *   `aead.py` implements `Sender.destroy()` and `Receiver.destroy()` which utilize `_zero_mutable_buffer` to wipe Python `bytearray` keys.
    *   `handshake.py` safely zeros `_shared_secret_buf` immediately after HKDF derivation.
    *   `async_proxy.py` uses a deferred destroy list (`_pending_destroy`) to safely wipe old cipher objects after the 5-second soft transition window expires, avoiding TOCTOU races.
5.  **Circuit Breaker:** A sliding window circuit breaker in `async_proxy.py` (`_rekey_cb_allow`) suppresses endless rekey loops if the peer is unresponsive, preventing localized DoS.

## 4. Conclusion and Technical Assessment

The `core/` directory is an exceptionally robust, production-grade implementation of a PQC proxy. It successfully synthesizes the high-throughput, low-overhead data plane design of **WireGuard** with the agile, post-quantum secure key exchange semantics of **TLS 1.3**.

The implementation shows a deep awareness of operational cryptography pitfalls, evidenced by the strict separation of replay window advancement from sequence checking, the explicit OOB handling of TCP controls to prevent thread starvation, and meticulous key lifecycle zeroization.

The architecture is fully validated against standard implementation guidelines and requires no immediate structural refactoring to meet the specified security or operational goals.
