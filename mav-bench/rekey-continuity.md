# AEAD Rekey Continuity

**Suite:** cs-mlkem768-mldsa65  
**AEAD:** aesgcm  
**Rate:** 50.0 Hz  
**Rekey Triggered:** Yes  
**Rekey OK:** Yes  

## Delivery by Window

| Window | Sent | Received | Delivery |
|--------|------|----------|----------|
| Pre Rekey | 500 | 500 | 100.0% |
| During Rekey | 250 | 250 | 100.0% |
| Post Rekey | 1751 | 1751 | 100.0% |
| Total | 2501 | 2501 | 100.0% |

**AEAD Continuous (≥95% delivery during rekey):** ✓ YES  

> A continuous result means the AEAD data plane maintains packet delivery through the
> key rotation window. This validates the epoch-based replay replay protection and
> atomic cipher swap implementation.