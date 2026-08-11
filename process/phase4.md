# Phase 4 End-to-End Run Documentation
## Detailed Record of This Exact Localhost Pipeline Run

Date: 2026-03-14  
Host: Windows workstation (localhost loopback)  
Environment: `conda run -n oqs-dev`  
Repository: `secure-tunnel`  
Scope: `core/` only

---

## 1) Objective

Document, end-to-end, the exact execution flow and observed outcomes for:

1. Runtime core rekey matrix validation (state-space and handshake/ratchet checks).
2. Live localhost pipeline validation with continuous traffic during rekey.

This document is evidence-based from generated artifacts in `logs/`.

---

## 2) What Was Executed

## 2.1 Static/runtime matrix validation

Command executed:

```powershell
conda run -n oqs-dev python tools/phase3_rekey_matrix_core.py
```

Artifact produced:

- [phase3_rekey_matrix_report.json](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/logs/phase3_core/phase3_rekey_matrix_report.json)

Observed summary:

- Runtime suites: `16` (HQC suites pruned by runtime capability)
- Runtime suite+AEAD states: `44`
- Total runtime transitions: `1936`
- Handshake checks: `16/16` pass
- AEAD-only ratchet checks: `80/80` pass
- Negotiation checks: `1936/1936` pass

---

## 2.2 Live loopback pipeline with traffic during rekey

Command executed:

```powershell
conda run -n oqs-dev python tools/phase3_loopback_e2e_states.py
```

Artifact produced:

- [phase3_loopback_summary.json](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/logs/phase3_loopback/phase3_loopback_summary.json)
- Per-case outputs in:
  - [same_suite_same_aead_l3](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/logs/phase3_loopback/same_suite_same_aead_l3)
  - [same_suite_aead_only_l3_gcm_to_ccm](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/logs/phase3_loopback/same_suite_aead_only_l3_gcm_to_ccm)
  - [same_suite_aead_only_l1_gcm_to_ascon](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/logs/phase3_loopback/same_suite_aead_only_l1_gcm_to_ascon)
  - [same_suite_aead_only_l5_gcm_to_chacha](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/logs/phase3_loopback/same_suite_aead_only_l5_gcm_to_chacha)
  - [diff_suite_same_level_l1](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/logs/phase3_loopback/diff_suite_same_level_l1)
  - [diff_suite_cross_level_l1_to_l5](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/logs/phase3_loopback/diff_suite_cross_level_l1_to_l5)

Observed summary:

- Total cases: `6`
- Passed: `4`
- Failed: `2`

---

## 3) How the E2E Runner Works (Exact Method)

Runner:

- [phase3_loopback_e2e_states.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/tools/phase3_loopback_e2e_states.py)

Execution strategy per case:

1. Build isolated config with loopback-only endpoints and unique per-case ports.
2. Start drone plaintext echo worker.
3. Start GCS proxy + Drone proxy threads (`run_proxy(...)`).
4. Wait for control-plane readiness (`cmd=ping` over TCP control).
5. Start continuous traffic worker:
  - send interval: `20ms`
  - payload format: `case_id|seq|timestamp`
  - expect exact echo from drone side.
6. Start status poll worker:
  - poll interval: `20ms`
  - collect `state`, `pending_suite`, `last_status`, `last_rekey_ms`.
7. Warmup traffic window.
8. Send rekey command:
  - `{"cmd":"rekey","suite":"<target_suite>","aead":"<target_aead>"}`
9. Observe until rekey completion condition or timeout.
10. Continue traffic in post-rekey window.
11. Stop workers, collect counters, write per-case JSON result.

Key config behavior in runner:

- `DRONE_HOST=GCS_HOST=127.0.0.1`
- `ENABLE_TCP_CONTROL=True`
- `CONTROL_COORDINATOR_ROLE="gcs"`
- `STRICT_HANDSHAKE_IP=False`
- `STRICT_UDP_PEER_MATCH=True`
- deterministic test PSK
- isolated ports per case (`base = 55000 + 40*index`)

---

## 4) Cases Tested in This Run

1. `same_suite_same_aead_l3`
2. `same_suite_aead_only_l3_gcm_to_ccm`
3. `same_suite_aead_only_l1_gcm_to_ascon`
4. `same_suite_aead_only_l5_gcm_to_chacha`
5. `diff_suite_same_level_l1`
6. `diff_suite_cross_level_l1_to_l5`

Categories covered:

- same suite, same AEAD
- same suite, AEAD-only shift
- different suite, same level
- different suite, cross-level

---

## 5) Pass/Fail Criteria Used

A case is marked pass only if all are true:

- control-plane became ready
- rekey command accepted and completed (`rekey_ok=true`)
- no proxy thread errors
- state sampling showed `RUNNING` plus transient evidence
- traffic continuity present in all windows:
  - `pre.ok > 0`
  - `during.ok > 0`
  - `post.ok > 0`

---

## 6) Detailed Results from This Run

## 6.1 Global

- elapsed wall time: `159.459s`
- category counts:
  - `same_suite_same_aead`: 1
  - `aead_only_same_suite`: 3
  - `full_handshake_same_level`: 1
  - `full_handshake_cross_level`: 1

## 6.2 Per-case outcome snapshot

`same_suite_same_aead_l3`:

- pass: `true`
- states: `NEGOTIATING`, `RUNNING`, `SWAPPING`
- traffic: pre `118/118`, during `11/11`, post `117/117`

`same_suite_aead_only_l3_gcm_to_ccm`:

- pass: `false`
- states: `NEGOTIATING`, `RUNNING`
- traffic: pre `117/117`, during `3/4`, post `0/15`
- drone counters include `rekeys_fail=1` while gcs has `rekeys_ok=1`

`same_suite_aead_only_l1_gcm_to_ascon`:

- pass: `true`
- states: `NEGOTIATING`, `RUNNING`
- traffic: pre `117/117`, during `1/1`, post `1/16` (degraded but non-zero continuity)

`same_suite_aead_only_l5_gcm_to_chacha`:

- pass: `false`
- states: `RUNNING` only (no transient sampled in this run)
- traffic: pre `117/117`, during `1/1`, post `0/15`
- drone counters include `rekeys_fail=1` while gcs has `rekeys_ok=1`

`diff_suite_same_level_l1`:

- pass: `true`
- states: `NEGOTIATING`, `RUNNING`
- traffic: pre `117/117`, during `12/12`, post `118/118`

`diff_suite_cross_level_l1_to_l5`:

- pass: `true`
- states: `RUNNING`, `SWAPPING`
- traffic: pre `117/117`, during `12/12`, post `117/117`

---

## 7) What This Run Confirms

Confirmed in this exact run:

- Full-handshake rekeys are stable under active traffic for tested same-level and cross-level paths.
- Same-suite same-AEAD rekey path preserved continuity.
- AEAD-only paths are not uniformly stable under load:
  - some AEAD-only transitions complete cleanly,
  - others show post-rekey blackout on loopback traffic with follower-side timeout recovery behavior.

Implication:

- AEAD-only rekey path still needs synchronization hardening before claiming uniformly robust continuity across all AEAD shifts.

---

## 8) Reproducibility Checklist

Prerequisites:

- `oqs-dev` conda env with `oqs` import working.
- Current repository state on branch `main`.

Commands:

```powershell
conda run -n oqs-dev python tools/phase3_rekey_matrix_core.py
conda run -n oqs-dev python tools/phase3_loopback_e2e_states.py
```

Expected outputs:

- `logs/phase3_core/phase3_rekey_matrix_report.json`
- `logs/phase3_loopback/phase3_loopback_summary.json`
- per-case JSON results under `logs/phase3_loopback/<case_id>/result.json`

---

## 9) Next Phase Recommendation

Priority next step:

- Add stricter dual-side control-state convergence for AEAD-only rekeys so follower cannot timeout while coordinator reports success.

Then rerun the same Phase 4 loopback suite and require:

- `6/6` case pass
- non-zero `post` continuity for all cases
- follower `rekeys_fail=0` on every AEAD-only case.

