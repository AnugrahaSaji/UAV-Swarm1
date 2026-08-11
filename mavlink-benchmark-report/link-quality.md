# MAVLink Link Quality Assessment

**Generated:** 2026-03-16T13:54:52.287670+00:00  
**Protocol version:** 1.0 (frozen)  

## Link Quality Matrix

| AEAD | HB Delivery | PING Delivery | PING P95 RTT (μs) | Stress Delivery | Rekey Continuous | Grade |
|------|------------|---------------|------------------|-----------------|------------------|-------|
| aesgcm128 | 100.0% | 100.0% | 1213.44 | 100.0% | ✓ | **A** |
| aesgcm192 | 100.0% | 100.0% | 1112.14 | 100.0% | ✓ | **A** |
| aesgcm256 | 100.0% | 100.0% | 1068.24 | 100.0% | ✓ | **A** |
| aesccm128 | 100.0% | 100.0% | 1067.74 | 100.0% | ✓ | **A** |
| aesccm192 | 100.0% | 100.0% | 1122.63 | 100.0% | ✓ | **A** |
| aesccm256 | 100.0% | 100.0% | 1430.61 | 100.0% | ✓ | **A** |
| ascon128 | 100.0% | 100.0% | 1190.52 | 100.0% | ✓ | **A** |
| chacha20poly1305 | 100.0% | 100.0% | 1045.75 | 100.0% | ✓ | **A** |

## Grading Criteria

| Grade | Criteria |
|-------|----------|
| **A** | All delivery metrics ≥ 99% AND rekey-continuous |
| **B** | All delivery metrics ≥ 95% |
| **C** | Any delivery metric < 95% |

## Connection Stability Summary

- AEADs tested    : 8 / 8
- Grade A         : 8 / 8
- Rekey-continuous: 8 / 8
- Stable operation: ALL PASS