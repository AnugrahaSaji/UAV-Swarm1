# Errors and Lessons: A Postmortem of the Secure Tunnel Project

## 1. Introduction

This document is an engineering postmortem. It details the "blood, sweat, and tears" behind the **Secure Tunnel** project. It exists because software development—especially distributed systems development—is rarely a straight line.

We faced a critical scenario: **A system that used to work perfectly started failing, despite being on the exact same commit.** This document explains why that happened, how we fixed it, and what we learned.

## 2. Early Design Challenges

*   **Architecture Decisions:** We initially struggled with where to place the "brains" of the operation. Should the GCS drive the test, or the Drone? We started with GCS-driven (`scheduler/`), but realized that in field tests, the Drone is the active agent. This led to the creation of `sscheduler/` (Drone-driven), but maintaining two orchestration logics caused confusion.
*   **UDP Bridging:** Bridging connectionless UDP to a stateful crypto stream is hard. We had to implement a "virtual connection" concept over UDP, handling timeouts and peer tracking manually.

## 3. Cryptography Integration Issues

*   **Suite Mismatches:** A frequent early bug was the GCS expecting `Kyber512` while the Drone sent `Kyber768`. This resulted in opaque "Decryption Failed" errors. We fixed this by adding a cleartext (but signed) header negotiation phase to the TCP handshake.
*   **Framing Failures:** PQC keys and ciphertexts are large. We initially fragmented packets incorrectly, leading to truncated keys and handshake hangs. We learned to use length-prefixed framing strictly for all TCP messages.

## 4. Scheduler & Orchestration Failures

*   **Race Conditions:** The GCS proxy takes time to initialize `liboqs`. The Drone would often try to connect before the GCS was listening. We added retry logic and explicit "Ready" states to the control protocol.
*   **Zombie Processes:** Old python processes (`sdrone.py`, `run_proxy.py`) would linger on the Pi, holding onto UDP ports. New runs would fail with "Address already in use" or, worse, silently bind to the wrong port. We implemented aggressive `pkill` cleanup routines.

## 5. Environment Drift Problems

*   **Conda vs Venv:** The GCS uses Conda; the Pi uses `venv`. We often forgot to activate the environment on one side, leading to `ModuleNotFoundError: oqs`.
*   **Sudo vs Non-Sudo:** On the Pi, we need `sudo` for real-time priority. However, `sudo python` strips environment variables (like `PYTHONPATH` or `LD_LIBRARY_PATH`). We learned to use `sudo -E` to preserve the user's environment.

## 6. Residue & State Haunting the System

This was the most painful lesson.

*   **`__pycache__`:** We would change a config value in `core/config.py`, pull the code, and run it. But Python would sometimes load the old compiled `.pyc` file if timestamps were wonky or permissions differed.
*   **Untracked Files:** We often created "temp" config files like `config_local.py` for debugging. These files would override the git-tracked config, causing the system to behave differently than the code suggested.
*   **The "Golden Commit" Fallacy:** We assumed that checking out a known-good commit hash meant the system would work. We were wrong. The *code* was the same, but the *state* (files on disk, installed libs, cache) was not.

## 7. Network & OS-Level Issues

*   **Strict Peer Matching:** We implemented a security feature: `STRICT_UDP_PEER_MATCH`. If the handshake came from IP `A`, we dropped UDP packets from IP `B`. This broke immediately on networks with dynamic routing or NAT, where the TCP and UDP paths differed.
*   **Firewalls:** Windows Defender silently blocked the new TCP port 46000. We spent hours debugging code before checking the firewall logs.

## 8. The “It Used to Work” Crisis

The project hit a crisis point. We had a demo configuration that worked on Tuesday. On Thursday, with no code changes, it failed.
*   **Symptoms:** Handshake success, but 100% packet loss on the UDP plane.
*   **Investigation:** We diffed the code. Identical. We checked the network. Identical.
*   **Realization:** We found a stale `__pycache__` directory on the Drone that contained an old version of the `Aead` class, incompatible with the GCS version.

## 9. The Breakthrough

The solution wasn't a code patch. It was a **process change**.

We introduced the **Sterile State Rule**:
> "Never trust a run unless the repo has been nuked and reset."

We mandated this command sequence before EVERY test:
```bash
git reset --hard HEAD
git clean -fdx
```
This deletes all untracked files, build artifacts, logs, and `__pycache__`.
Once we enforced this, the "ghosts" disappeared. The system became deterministic again.

## 10. Final Root Causes

1.  **State Contamination:** Python bytecode (`.pyc`) and untracked config overrides caused the running code to differ from the source code.
2.  **Environment Drift:** Subtle differences in library versions between machines.
3.  **Implicit Assumptions:** Assuming "no error message" meant "success" (it often meant silent drops).

## 11. Hardening the Workflow

We hardened the project by:
*   **Automation:** Adding cleanup scripts that run `git clean -fdx` automatically.
*   **Observability:** Adding `status.json` outputs that dump the *actual* loaded config at runtime, so we can verify what the program *thinks* it's running.
*   **Explicit Logging:** Logging every packet drop reason (Auth, Replay, Header) instead of just "Drop".

## 12. Lessons Learned

*   **Evidence over Assumption:** Don't assume the config is loaded. Log it. Don't assume the port is open. Test it.
*   **The "Clean Room" Approach:** In distributed systems, you cannot debug effectively if the environment is dirty. Sterility is a prerequisite for debugging.
*   **System-Level Thinking:** The bug is often not in the Python code, but in the interaction between Python, the OS, the Network, and the File System.

## 13. Advice to Future Developers

*   **Nuke it:** If you are confused, `git clean -fdx`.
*   **Check Time:** Ensure clocks are synced.
*   **Read the Logs:** We write detailed logs for a reason. If packets are dropping, the logs usually say *why* (e.g., "Replay window violation").
*   **One Change at a Time:** Never change the GCS code and Drone code simultaneously while debugging. Pin one, fix the other.

## 14. Closing Note

This project was a journey from "it works on my machine" to "it works on a distributed, embedded, crypto-agile network." The pain of debugging these failures has made the final system robust, reliable, and truly secure.
