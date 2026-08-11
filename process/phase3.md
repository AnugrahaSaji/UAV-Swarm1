# Phase 3 - Core Rekey Combination Validation

Date: 2026-03-14  
Env: `conda run -n oqs-dev`  
Scope: `core/` only

---

## 1) Direct answer to your key question

### Where signing identity keys are used

Signing keys are used only for authentication in handshake, not for HKDF key expansion.

- GCS signs handshake transcript: `server_sig_obj.sign(transcript)` in [core/handshake.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/handshake.py:368)
- Drone verifies signature: `sig.verify(...)` in [core/handshake.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/handshake.py:428)
- Per-suite key loaders are defined in:
  - [core/run_proxy.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/run_proxy.py:299) (`_build_matrix_secret_loader`)
  - [core/run_proxy.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/run_proxy.py:391) (`_build_matrix_public_loader`)
- Per-suite signing keys are pulled during rekey when suite changes:
  - GCS secret load: [core/async_proxy.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/async_proxy.py:1456)
  - Drone public load: [core/async_proxy.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/async_proxy.py:1515)

### Are signing keys used in HKDF derive?

No. HKDF derive uses:

- `shared_secret`
- `session_id`
- `challenge`
- `kem_name` + `sig_name` labels
- `epoch`
- PSK mix

See [core/handshake.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/handshake.py:133), info construction at [core/handshake.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/handshake.py:164), salt at [core/handshake.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/handshake.py:165).

So:

- `24 suites` are profile identities (`kem x ds`) used for algorithm selection and transcript labeling.
- Signing private/public key material is used for sign/verify only, not as HKDF input bytes.

---

## 2) AEAD landscape and total combinations

Implemented level-aware AEAD policy matrix:

- `L1`: `aesgcm`, `aesccm`, `ascon128a` (3)
- `L3`: `aesgcm`, `aesccm` (2)
- `L5`: `aesgcm`, `aesccm`, `chacha20poly1305` (3)

Defined in [core/suites.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/suites.py:583) via `_AEAD_PROFILES_BY_LEVEL` and exposed by [core/suites.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/suites.py:590).

Canonical suite count:

- `24` (`kem x ds`, level-aligned) from [core/suites.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/suites.py:547)

Canonical suite+AEAD state count:

- `66` states
- Formula: `L1(9 suites*3) + L3(6*2) + L5(9*3) = 66`

Canonical total rekey transitions (state->state):

- `66 x 66 = 4356`

Canonical transition breakdown:

- `same_suite_same_aead`: `66`
- `aead_only_same_suite`: `120`
- `full_handshake_same_level`: `1416`
- `full_handshake_cross_level`: `2754`

Current runtime (this PC in `oqs-dev`) after suite prune:

- `16` suites available (HQC suites pruned by runtime support)
- `44` runtime states
- `44 x 44 = 1936` runtime transitions

Runtime transition breakdown (measured):

- `same_suite_same_aead`: `44`
- `aead_only_same_suite`: `80`
- `full_handshake_same_level`: `588`
- `full_handshake_cross_level`: `1224`

---

## 3) Rekey path semantics (what exactly happens)

### Same suite + same AEAD

- Classified as no AEAD delta, so **full handshake path** is used (not ratchet).
- Decision logic in [core/async_proxy.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/async_proxy.py:1614) and [core/async_proxy.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/async_proxy.py:1623).

### Same suite + different AEAD

- **AEAD-only ratchet path** using `derive_aead_ratchet(...)` in [core/handshake.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/handshake.py:191), called from [core/async_proxy.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/async_proxy.py:1624).
- New token applied atomically during context swap at [core/async_proxy.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/core/async_proxy.py:1709).

### Different suite (same level or cross-level)

- **Full handshake path**.
- Per-suite signing credentials are loaded via matrix loaders if provided.

---

## 4) Phase 3 tests executed

I added and executed:

- Script: [tools/phase3_rekey_matrix_core.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/tools/phase3_rekey_matrix_core.py)
- Command: `conda run -n oqs-dev python tools/phase3_rekey_matrix_core.py`
- JSON report: [logs/phase3_core/phase3_rekey_matrix_report.json](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/logs/phase3_core/phase3_rekey_matrix_report.json)

What this validates:

1. Runtime suite inventory and AEAD level profiles.
2. Handshake success for every runtime suite (`server_gcs_handshake` + `client_drone_handshake`).
3. Exhaustive runtime state-space transition classification.
4. AEAD-only ratchet checks for every same-suite AEAD shift.
5. Negotiation guard checks over every runtime transition.

Measured outcomes:

- Handshake: `16/16` passed
- AEAD-only ratchet: `80/80` passed
- Negotiation checks: `1936/1936` passed
- No failures recorded in this Phase 3 run.

---

## 5) Progress status and next action

Core Phase 3 validation is complete for current runtime capabilities on this host.

Important runtime note:

- This host currently prunes all HQC suites at runtime, so empirical run is on `16` suites, not full `24`.
- Canonical math for full design-space (`24 suites`, `66 states`, `4356 transitions`) is included above and verified by static enumeration.

Next practical step for your full-paper claim:

- Run the same Phase 3 script on the environment where HQC is enabled so runtime suite count reaches `24`, then regenerate the report to get full empirical `4356` transition coverage.

---

## 6) Phase 3B - Loopback End-to-End Pipeline Under Live Rekey

Per your request, I added a second Phase 3 track focused on true localhost pipeline behavior (app->proxy->encrypted UDP->peer->app echo) while rekey is executed.

### 6.1 Runner and artifacts

- Runner script: [tools/phase3_loopback_e2e_states.py](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/tools/phase3_loopback_e2e_states.py)
- Summary artifact: [logs/phase3_loopback/phase3_loopback_summary.json](c:/Users/ashis/OneDrive/Desktop/secure-tunnel/logs/phase3_loopback/phase3_loopback_summary.json)
- Per-case artifact folder: `logs/phase3_loopback/<case_id>/result.json`

### 6.2 What this E2E runner validates

For each case:

1. Start GCS and Drone proxy on loopback with isolated ports.
2. Keep continuous request/echo UDP traffic running from GCS plaintext side.
3. Trigger rekey by TCP control command (`cmd=rekey`) on GCS control endpoint.
4. Poll control state transitions during rekey.
5. Split traffic into `pre`, `during`, `post` windows and compute success/loss.

Pass criteria per case:

- control ready
- rekey accepted and reported complete
- transient states sampled (`RUNNING` + transient state evidence)
- traffic continuity present in `pre`, `during`, and `post`

### 6.3 Cases executed

1. `same_suite_same_aead_l3`
2. `same_suite_aead_only_l3_gcm_to_ccm`
3. `same_suite_aead_only_l1_gcm_to_ascon`
4. `same_suite_aead_only_l5_gcm_to_chacha`
5. `diff_suite_same_level_l1`
6. `diff_suite_cross_level_l1_to_l5`

### 6.4 Measured result summary

Global:

- total cases: `6`
- passed: `4`
- failed: `2`

Per case:

- `same_suite_same_aead_l3`: pass
  - pre `118/118`, during `11/11`, post `117/117`
  - observed states: `RUNNING`, `SWAPPING`
- `same_suite_aead_only_l3_gcm_to_ccm`: fail
  - pre `117/117`, during `3/4`, post `0/15`
  - observed states: `NEGOTIATING`, `RUNNING`
- `same_suite_aead_only_l1_gcm_to_ascon`: pass
  - pre `117/117`, during `1/1`, post `1/16`
  - observed states sampled and post continuity minimal but non-zero
- `same_suite_aead_only_l5_gcm_to_chacha`: fail
  - pre `117/117`, during `1/1`, post `0/15`
  - observed state collapsed to `RUNNING` only in this run
- `diff_suite_same_level_l1`: pass
  - pre `117/117`, during `12/12`, post `118/118`
  - observed states: `RUNNING`, `SWAPPING`
- `diff_suite_cross_level_l1_to_l5`: pass
  - pre `117/117`, during `12/12`, post `117/117`
  - observed states: `NEGOTIATING`, `RUNNING`, `SWAPPING`

### 6.5 Key observation from E2E loopback

Full-handshake transitions are stable in this run:

- same-suite same-AEAD full-handshake
- different-suite same-level
- different-suite cross-level

AEAD-only transitions are mixed:

- one AEAD-only case passed with low post volume
- two AEAD-only cases showed `post=0` continuity after local rekey completion on coordinator side

Correlated runtime logs in failing AEAD-only runs show follower-side timeout recovery:

- `Control state timeout recovery triggered` on drone with `timeout_negotiating`

This means there is a real synchronization gap in some AEAD-only paths under live traffic: coordinator can mark rekey success while follower control state later times out.

### 6.6 Impact for next core pass

Before claiming AEAD-only rekey as fully production-stable in paper results, core should add stricter commit/ack synchronization for AEAD-only path so both sides converge control state and data continuity consistently under load.
