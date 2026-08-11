# MAVLink Tunnel Benchmark — All-AEAD Summary

**Date:** 2026-03-16T12:21:08.226658+00:00  
**Host:** uavpi  
**Platform:** Linux-6.12.47+rpt-rpi-v8-aarch64-with-glibc2.36  
**Suite:** multi-level  
**Protocol version:** 1.0 (frozen)  

## Per-AEAD Quick Results

| AEAD | HB % | PING Mean (μs) | PING P95 (μs) | Stress % | Rekey OK | Continuous |
|------|------|---------------|--------------|----------|----------|------------|
| aesgcm128 | 100.0% | 768.06 | 1213.44 | 100.0% | ✓ | ✓ YES |
| aesgcm192 | 100.0% | 712.91 | 1112.14 | 100.0% | ✓ | ✓ YES |
| aesgcm256 | 100.0% | 698.15 | 1068.24 | 100.0% | ✓ | ✓ YES |
| aesccm128 | 100.0% | 707.13 | 1067.74 | 100.0% | ✓ | ✓ YES |
| aesccm192 | 100.0% | 743.98 | 1122.63 | 100.0% | ✓ | ✓ YES |
| aesccm256 | 100.0% | 813.74 | 1430.61 | 100.0% | ✓ | ✓ YES |
| ascon128 | 100.0% | 794.85 | 1190.52 | 100.0% | ✓ | ✓ YES |
| chacha20poly1305 | 100.0% | 668.74 | 1045.75 | 100.0% | ✓ | ✓ YES |