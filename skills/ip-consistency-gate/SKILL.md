---
description: Preflight safety gate — verify host role, active profile, and observed IPs before any networked secure-tunnel run
---

# IP Consistency Gate Skill

**Scope:** `devtools/ip_consistency_check.py`, `.genv`, `.denv`, `core/config.py`, `docs/lab-ops-gcs-pi.md`

## Purpose
Prevent invalid or misleading runs caused by running with the wrong host role (GCS vs Drone) or mismatched network profile (LAN vs Tailscale vs localhost).

## Non-Negotiables
- Run the gate before any networked benchmark, E2E validation, or paper claim.
- If the gate reports ambiguity or mismatch, stop and resolve it before proceeding.

## How To Run
From the repo root:
- On Windows (GCS): `python devtools/ip_consistency_check.py --role gcs`
- On Pi (Drone): `python3 devtools/ip_consistency_check.py --role drone`

## What Must Be Recorded
Capture and include in your run manifest:
- host role used (`gcs` or `drone`)
- active `TUNNEL_HOST_PROFILE`
- expected LAN/Tailscale hosts from config
- observed local IPv4 addresses detected on the machine

## Interpretation Rules
- PASS means: imports + config parsing succeeded, and the output is internally consistent.
- WARN means: the script ran, but local observed IPs do not match the configured profile/hosts. Treat WARN as a hard stop for benchmarking unless you explicitly document the reason (e.g., multi-NIC host, VPN, captive portal).
## Global Lab Context (recommended)
To avoid hard-coded IPs and to keep all agents consistent, maintain a single machine-local lab context file:
- Windows: %USERPROFILE%\.claude\lab\secure-tunnel-lab.json
- Linux/macOS: ~/.claude/lab/secure-tunnel-lab.json

Template: docs/lab-context.template.json

