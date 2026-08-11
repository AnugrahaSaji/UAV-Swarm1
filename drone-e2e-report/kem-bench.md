# KEM Benchmark

Correctness: each encapsulated shared secret matched decapsulation output.
Time source: time.perf_counter_ns().

| Algorithm | PK (B) | CT (B) | SS (B) | KeyGen mean (us) | Encap mean (us) | Decap mean (us) | KeyGen p95 (us) | Encap p95 (us) | Decap p95 (us) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ML-KEM-512 | 800 | 768 | 32 | 52.32 | 59.82 | 64.67 | 53.28 | 63.07 | 65.63 |
| ML-KEM-768 | 1184 | 1088 | 32 | 77.76 | 84.71 | 92.64 | 78.91 | 85.65 | 95.19 |
| ML-KEM-1024 | 1568 | 1568 | 32 | 107.11 | 116.33 | 128.82 | 110.37 | 119.74 | 132.13 |
