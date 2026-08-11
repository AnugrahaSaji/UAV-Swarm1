# GCS Benchmark Summary

## Scope
- Frozen core benchmark campaign executed without modifying protocol semantics.
- Timings collected with time.perf_counter_ns() in benchmark harness.
- Correctness gates applied before accepting timing samples.

## Environment
- Host: uavpi
- OS: Linux 6.12.47+rpt-rpi-v8 (#1 SMP PREEMPT Debian 1:6.12.47-1+rpt1~bookworm (2025-09-16))
- Python: 3.11.2 (main, Apr 28 2025, 14:11:48) [GCC 12.2.0]
- OpenSSL: OpenSSL 3.0.17 1 Jul 2025
- OQS Python: unknown
- liboqs: unknown

## Coverage
- KEM algorithms: ML-KEM-512, ML-KEM-768, ML-KEM-1024
- Signature algorithms: ML-DSA-44, ML-DSA-65, ML-DSA-87, SPHINCS+-SHA2-128s-simple
- AEAD algorithms: aesccm128, aesccm192, aesccm256, aesgcm128, aesgcm192, aesgcm256, ascon128, ascon128a, chacha20poly1305
- AEAD payload sizes: 64, 256, 1024, 4096 bytes
- E2E localhost packets: 5000

## E2E Validation
- Success flag: True
- Received/Sent: 5000/5000
- Timeouts: 0
- Mean RTT (us): 818.63

## Report Files
- environment.md
- kem-bench.md
- signature-bench.md
- aead-bench.md
- e2e-localhost.md
- benchmark-summary.md
