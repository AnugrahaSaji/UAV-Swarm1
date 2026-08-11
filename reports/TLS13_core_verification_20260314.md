# TLS 1.3 / PQC Core Verification Report (2026-03-14)

## Scope
- Code paths reviewed:
  - core/handshake.py
  - core/aead.py
  - core/async_proxy.py
  - core/control_tcp.py
  - core/policy_engine.py
  - core/metrics_aggregator.py
  - sscheduler/common.py
  - sscheduler/sdrone_bench.py
  - sscheduler/benchmark_policy.py
- Standards references used for alignment:
  - RFC 8446 (TLS 1.3)
  - FIPS 203 (ML-KEM)
  - FIPS 204 (ML-DSA)
  - FIPS 205 (SLH-DSA)

## Execution Path Locked
- active_scheduler_path:
  - Drone benchmark entry: sscheduler/sdrone_bench.py
  - GCS benchmark control: sscheduler/sgcs_bench.py
  - Mode resolver: sscheduler/common.py
  - Control commands: start_proxy, collect_metrics/stop_suite, prepare_rekey
- ordering_invariants (confirmed):
  - MAVPROXY-only mode is enforced and mode conflicts are rejected.
  - In-band rekey defers suite index advance until rekey success.
  - Failed rekey paths restore old-suite metrics context and do not commit advance.

## Transport Validation (core-transport-validation)
- validated_paths:
  - Drop counter lifecycle and classification in core/async_proxy.py
  - Rekey result accounting in core/async_proxy.py + core/policy_engine.py
  - Strict peer match gating in core/async_proxy.py
  - OOB control authorization and coordinator checks in core/control_tcp.py
  - HKDF transcript/PSK/epoch binding in core/handshake.py
  - AEAD nonce construction and replay window semantics in core/aead.py
- invariants_confirmed:
  - confirmed: replay/auth/header/session/src_addr drops are distinctly counted and exported.
  - confirmed: STRICT_UDP_PEER_MATCH controls IP+port vs IP-only acceptance.
  - confirmed: control-plane rekey requires authorized peer + coordinator role.
  - confirmed: active rekey duplicate suppression and failure/success accounting exist.
  - confirmed: key derivation binds session_id, challenge, kem_name, sig_name, PSK digest, and epoch.
  - confirmed: ratchet path uses explicit epoch and AEAD token binding in HKDF info labels.
- invariants_broken:
  - none confirmed.
- open_unknowns:
  - unknown: constant-time behavior of all liboqs/pysodium backend primitives at runtime on all targets.
  - unknown: operational anti-replay posture of distributed deployment zones (single-zone vs multi-zone acceptance).

## Metrics Reconciliation (metrics-truth-reconciliation)
- formula_map:
  - packet_loss_ratio = (drop_replay + drop_auth + drop_header) / packets_sent
- included_counters:
  - drop_replay, drop_auth, drop_header
- excluded_counters:
  - drop_session_epoch, drop_src_addr, drop_other, sniff_drop
- semantic_mismatches:
  - confirmed: packet_loss_ratio is not total-drop ratio unless excluded classes are explicitly added.
- reconciled_statement:
  - packet_loss_ratio is a crypto-decode loss ratio, not an end-to-end total loss KPI.

## Standards Alignment
- TLS 1.3 model alignment:
  - confirmed: suite identity split from AEAD is aligned with RFC 8446 separation of key exchange/authentication from record AEAD.
  - confirmed: KDF uses HKDF and context binding consistent with transcript-bound derivation principles.
  - confirmed: per-record AEAD framing includes authenticated header and deterministic nonce from epoch+sequence, matching nonce uniqueness intent.
  - confirmed: key-update style ratchet is present (epoch-based re-derivation) for runtime profile changes.
- NIST PQC alignment:
  - confirmed: KEM/SIG registry model explicitly maps to ML-KEM and ML-DSA family levels and supports SLH-DSA variants.
  - likely: level pairing policy is operationally reasonable, but formal compliance claims require test vectors + certification profile artifacts beyond code inspection.

## Hardening Delta Applied
- sscheduler/sdrone_bench.py:
  - handshake/rekey status waits now use CONFIG[REKEY_HANDSHAKE_TIMEOUT] through DEFAULT_REKEY_TIMEOUT_S.
  - explicit custom suite sequence support added:
    - --suite-sequence-file (JSON array)
    - --suite-sequence (comma-separated)
  - sequence validation rejects unknown suite IDs before benchmark run.
  - result AEAD metadata now prefers aead_token field.
- tools/rekey_benchmark_matrix.py (new):
  - generates 24-suite rekey scenario files:
    - same_suite_rekey
    - same_level_rekey
    - cross_level_rekey
  - supports optional execution via sscheduler.sdrone_bench in in_band_rekey mode.

## Benchmark Readiness
- 24-suite matrix inputs generated at:
  - logs/rekey_matrix/same_suite_rekey.json
  - logs/rekey_matrix/same_level_rekey.json
  - logs/rekey_matrix/cross_level_rekey.json
  - logs/rekey_matrix/manifest.json
- validated end-to-end dry-run:
  - sdrone_bench successfully loads a 144-entry explicit sequence in in_band_rekey mode.

## Final Verdict
- transport_verdict: pass_with_risk
- scheduler_verdict: pass
- metrics_verdict: pass_with_risk
- cross_agent_conflicts: none
- final_verdict: pass_with_risk
- required_next_actions:
  - run the three generated scenarios on live GCS+drone and collect comprehensive metrics outputs.
  - when reporting packet loss externally, publish both crypto-loss and total-drop formulas.
  - if claiming formal standards compliance, add vector-based evidence against FIPS/RFC conformance profiles.
