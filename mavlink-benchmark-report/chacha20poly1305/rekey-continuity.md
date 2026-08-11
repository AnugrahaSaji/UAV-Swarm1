# AEAD Rekey Continuity

**Suite:** cs-mlkem1024-mldsa87  
**AEAD:** chacha20poly1305  
**Rate:** 50.0 Hz  
**Rekey Triggered:** Yes  
**Rekey OK:** Yes  

## Delivery by Window

| Window | Sent | Received | Delivery |
|--------|------|----------|----------|
| Pre Rekey | 15001 | 15001 | 100.0% |
| During Rekey | 250 | 250 | 100.0% |
| Post Rekey | 14750 | 14750 | 100.0% |
| Total | 30001 | 30001 | 100.0% |

**AEAD Continuous (≥95% delivery during rekey):** ✓ YES  

> A continuous result means the AEAD data plane maintains packet delivery through the
> key rotation window. This validates the epoch-based replay replay protection and
> atomic cipher swap implementation.