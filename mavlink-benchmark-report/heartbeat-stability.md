# MAVLink Heartbeat Stability

**Generated:** 2026-03-16T13:54:52.287176+00:00  
**Test:** 1 Hz HEARTBEAT for 60 s per AEAD  

## Heartbeat Continuity by AEAD

| AEAD | Sent | Received | Delivery % | RTT Mean (ms) | RTT P95 (ms) | Interval Stdev (ms) | Status |
|------|------|----------|-----------|--------------|-------------|-------------------|--------|
| aesgcm128 | 60 | 60 | 100.0% | 1.011 | 1.193 | 0.258 | **PASS** |
| aesgcm192 | 60 | 60 | 100.0% | 1.168 | 1.367 | 0.26 | **PASS** |
| aesgcm256 | 60 | 60 | 100.0% | 1.122 | 1.418 | 0.388 | **PASS** |
| aesccm128 | 60 | 60 | 100.0% | 1.065 | 1.326 | 0.253 | **PASS** |
| aesccm192 | 60 | 60 | 100.0% | 1.169 | 1.414 | 0.191 | **PASS** |
| aesccm256 | 60 | 60 | 100.0% | 1.018 | 1.308 | 0.115 | **PASS** |
| ascon128 | 60 | 60 | 100.0% | 1.156 | 1.47 | 0.364 | **PASS** |
| chacha20poly1305 | 60 | 60 | 100.0% | 1.05 | 1.339 | 0.335 | **PASS** |

## Interpretation

| Status | Criteria |
|--------|----------|
| **PASS** | ≥ 99% delivery with stable 1 Hz interval |
| **DEGRADED** | ≥ 95% delivery |
| **FAIL** | < 95% delivery — tunnel instability detected |