# Localhost End-to-End Benchmark

Suite: cs-mlkem768-mldsa65
Packets requested: 5000
Run success: True
Integrity check (received == sent): True
Time source in tunnel metrics: internal counters + RTT timings from time.perf_counter_ns().

| Metric | Value |
| --- | --- |
| aead_token | aesgcm |
| drone_aead_decrypt_ms | 0.045698 |
| drone_aead_encrypt_ms | 0.029447 |
| drone_drops | 5 |
| drone_enc_in | 5005 |
| drone_enc_out | 5012 |
| drone_handshake_ms | 13.1148 |
| echo_resets | 0 |
| echoed | 5000 |
| gcs_aead_decrypt_ms | 0.036636 |
| gcs_aead_encrypt_ms | 0.043972 |
| gcs_drops | 6 |
| gcs_enc_in | 5012 |
| gcs_enc_out | 5005 |
| gcs_handshake_ms | 13.4511 |
| kem | ML-KEM-768 |
| nist_level | L3 |
| received | 5000 |
| resets | 0 |
| rtt_max_us | 5403.85 |
| rtt_mean_us | 818.63 |
| rtt_median_us | 763.77 |
| rtt_p95_us | 1339.76 |
| sent | 5000 |
| sig | ML-DSA-65 |
| success | True |
| suite | cs-mlkem768-mldsa65 |
| timeouts | 0 |
