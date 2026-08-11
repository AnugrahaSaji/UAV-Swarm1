# Core Freeze and Experimental Phase Baseline

Date: 2026-03-16

## 1. Core Freeze Confirmation

The secure MAVLink tunnel core is frozen after completion of:
- protocol extraction and specification
- protocol conformance validation
- NIST and Open Quantum Safe cryptographic validation
- implementation invariant verification
- state-machine correctness verification
- control-plane and data-plane interaction safety analysis

Frozen components:
- core/handshake.py
- core/aead.py
- core/async_proxy.py
- core/control_tcp.py
- core/policy_engine.py
- core/suites.py
- secure_tunnel_protocol_spec.md

Frozen protocol properties:
- handshake message sequence
- AEAD packet format
- nonce construction (epoch + sequence)
- replay window algorithm
- rekey lifecycle (prepare -> commit -> activate)
- control-plane message semantics
- suite registry structure

Post-freeze constraints:
- No changes are permitted to packet header format, nonce generation logic, HKDF key schedule inputs, replay window algorithm, or epoch progression rules.
- Only critical bug fixes that preserve protocol semantics are allowed without explicit protocol revision approval.

## 2. Protocol Version Definition

Validated baseline identifier:
- PROTOCOL_VERSION = 1.0

Interpretation:
- Version 1.0 is the canonical validated protocol baseline for all deterministic validation and benchmarking campaigns.
- All experimental findings must be attributable to this frozen baseline unless a formal protocol revision is approved.

## 3. Experimental Phase Plan

### 3.1 Deterministic Validation Tests

Scenarios to implement and execute on the frozen baseline:
- packet loss
- packet reordering
- replay attempts
- delayed control messages
- sequence exhaustion
- rekey race conditions

Validation objective:
- confirm runtime behavior remains consistent with secure_tunnel_protocol_spec.md under adversarial transport conditions.

### 3.2 Localhost Tunnel Validation

Single-machine end-to-end topology:
- GCS proxy -> UDP tunnel -> drone proxy

Measurements:
- handshake latency
- AEAD encryption/decryption cost
- packet round-trip latency

Validation objective:
- establish deterministic baseline behavior before hardware deployment.

### 3.3 Hardware Benchmark Preparation (Raspberry Pi)

Target measurements:
- PQC handshake cost
- AEAD throughput
- CPU utilization
- power consumption

Validation objective:
- quantify deployment viability on companion-computer hardware under frozen protocol semantics.

### 3.4 Scheduler Evaluation

Enable scheduler-layer experimentation for:
- suite selection logic
- runtime rekey policy behavior
- NIST security-level switching
- telemetry-driven decision paths

Validation objective:
- evaluate policy effectiveness without altering frozen transport/crypto semantics.

## 4. Governance for Benchmarking Campaign

- Experimental work must operate on the frozen core implementation.
- Any deviation from PROTOCOL_VERSION 1.0 requires explicit protocol revision approval.
- Reports and plots must state protocol version and freeze baseline alignment.
