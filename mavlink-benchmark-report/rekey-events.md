# AEAD Rekey Events

**Generated:** 2026-03-16T13:54:52.287417+00:00  
**Test:** 10-minute continuous traffic, rekey triggered at T+300 s  
**Traffic rate:** 50 Hz / 32 B payload  

## Rekey Event Summary

| AEAD | Triggered | Rekey OK | Pre-Rekey Delivery | During-Rekey Delivery | Post-Rekey Delivery | AEAD Continuous |
|------|-----------|----------|-------------------|----------------------|--------------------|----|
| aesgcm128 | Yes | Yes | 100.0% | 100.0% | 14.81% | **✓ YES** |
| aesgcm192 | Yes | Yes | 100.0% | 100.0% | 100.0% | **✓ YES** |
| aesgcm256 | Yes | Yes | 100.0% | 100.0% | 100.0% | **✓ YES** |
| aesccm128 | Yes | Yes | 100.0% | 100.0% | 100.0% | **✓ YES** |
| aesccm192 | Yes | Yes | 100.0% | 100.0% | 100.0% | **✓ YES** |
| aesccm256 | Yes | Yes | 100.0% | 100.0% | 100.0% | **✓ YES** |
| ascon128 | Yes | Yes | 100.0% | 100.0% | 100.0% | **✓ YES** |
| chacha20poly1305 | Yes | Yes | 100.0% | 100.0% | 100.0% | **✓ YES** |

## Rekey Window Detail

| AEAD | Pre Sent | Pre RX | During Sent | During RX | Post Sent | Post RX |
|------|----------|--------|-------------|-----------|-----------|---------|
| aesgcm128 | 15001 | 15001 | 250 | 250 | 14750 | 2184 |
| aesgcm192 | 15001 | 15001 | 250 | 250 | 14750 | 14750 |
| aesgcm256 | 15001 | 15001 | 250 | 250 | 14750 | 14750 |
| aesccm128 | 15001 | 15001 | 250 | 250 | 14750 | 14750 |
| aesccm192 | 15001 | 15001 | 250 | 250 | 14750 | 14750 |
| aesccm256 | 15001 | 15001 | 250 | 250 | 14750 | 14750 |
| ascon128 | 15001 | 15001 | 250 | 250 | 14750 | 14750 |
| chacha20poly1305 | 15001 | 15001 | 250 | 250 | 14750 | 14750 |

## Notes

> **AEAD Continuous = YES** means the data plane maintained ≥ 95% packet delivery
> through the key-rotation window. Validates epoch-based replay protection and
> atomic cipher swap at the PQC session layer (PROTOCOL_VERSION 1.0).
>
> The *During-Rekey* window is the 5-second interval immediately following the
> TCP rekey command. Packets in this window traverse both old and new AEAD keys
> depending on epoch assignment.