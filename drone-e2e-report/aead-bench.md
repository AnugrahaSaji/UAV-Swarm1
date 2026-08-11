# AEAD Benchmark

Correctness: decrypted payload matched original plaintext for all timed iterations.
Time source: time.perf_counter_ns().

| Algorithm | Payload (B) | Encrypt mean (us) | Decrypt mean (us) | Encrypt p95 (us) | Decrypt p95 (us) |
| --- | --- | --- | --- | --- | --- |
| aesgcm128 | n/a | n/a | n/a | n/a | unsupported_on_host: unknown AEAD token: aesgcm128 |
| aesgcm192 | n/a | n/a | n/a | n/a | unsupported_on_host: unknown AEAD token: aesgcm192 |
| aesgcm256 | n/a | n/a | n/a | n/a | unsupported_on_host: unknown AEAD token: aesgcm256 |
| aesccm128 | n/a | n/a | n/a | n/a | unsupported_on_host: unknown AEAD token: aesccm128 |
| aesccm192 | n/a | n/a | n/a | n/a | unsupported_on_host: unknown AEAD token: aesccm192 |
| aesccm256 | n/a | n/a | n/a | n/a | unsupported_on_host: unknown AEAD token: aesccm256 |
| chacha20poly1305 | 64 | 11.06 | 13.27 | 11.30 | 13.48 |
| chacha20poly1305 | 256 | 12.26 | 14.76 | 12.46 | 14.93 |
| chacha20poly1305 | 1024 | 16.03 | 18.23 | 16.26 | 18.48 |
| chacha20poly1305 | 4096 | 26.09 | 28.75 | 26.30 | 28.87 |
| ascon128 | 64 | 19.54 | 21.84 | 19.96 | 22.13 |
| ascon128 | 256 | 20.24 | 22.59 | 20.50 | 22.87 |
| ascon128 | 1024 | 25.23 | 27.69 | 25.61 | 28.02 |
| ascon128 | 4096 | 38.74 | 40.99 | 38.89 | 41.22 |
| ascon128a | 64 | 10.13 | 12.69 | 10.37 | 12.94 |
| ascon128a | 256 | 11.09 | 14.00 | 11.26 | 14.30 |
| ascon128a | 1024 | 15.13 | 17.99 | 15.41 | 18.30 |
| ascon128a | 4096 | 27.41 | 31.01 | 27.67 | 31.24 |
