# Secure-Tunnel Lab Context (Global)

This repo uses **one shared, machine-local** file to store lab-specific values (IPs, Tailscale names, SSH user, and repo paths on the Pi).

## Files
- Template (tracked): `docs/lab-context.template.json`
- Local override (NOT tracked):
  - Windows: `%USERPROFILE%\.claude\lab\secure-tunnel-lab.json`
  - Linux/macOS: `~/.claude/lab/secure-tunnel-lab.json`

## Why
- Prevent hard-coded lab IPs inside skills/docs.
- Keep benchmarks reproducible by recording the exact runtime environment.

## How to use
1. Copy the template to your local override path above.
2. Fill in fields for GCS + Drone.
3. For any networked run, run the IP gate first:
   - `python devtools/ip_consistency_check.py --role gcs`
   - `python3 devtools/ip_consistency_check.py --role drone`
4. Record the filled values (or a redacted subset) in your run manifest.

## Repo policy
- Do **not** commit the filled-in file.
- The repo template may evolve; local overrides are per-user/per-lab.