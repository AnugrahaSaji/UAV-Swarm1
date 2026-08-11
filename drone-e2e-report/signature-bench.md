# Signature Benchmark

Correctness: each signature verified successfully with generated public key.
Time source: time.perf_counter_ns().

| Algorithm | PK (B) | SIG (B) | KeyGen mean (us) | Sign mean (us) | Verify mean (us) | KeyGen p95 (us) | Sign p95 (us) | Verify p95 (us) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ML-DSA-44 | 1312 | 2420 | 224.22 | 985.83 | 240.78 | 229.11 | 2359.14 | 247.48 |
| ML-DSA-65 | 1952 | 3309 | 408.28 | 1668.67 | 402.61 | 463.09 | 3900.84 | 464.37 |
| ML-DSA-87 | 2592 | 4627 | 585.40 | 1854.74 | 607.37 | 594.04 | 3773.84 | 618.34 |
| SPHINCS+-SHA2-128s-simple | 32 | 7856 | 193618.03 | 1471671.99 | 1510.04 | 195779.95 | 1479535.93 | 1604.86 |
