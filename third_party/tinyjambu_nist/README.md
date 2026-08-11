# TinyJambu-192 — Official NIST LWC Submission Code

This directory contains the **official optimized C implementation** of
TinyJambu-192 AEAD as submitted to the NIST Lightweight Cryptography (LWC)
Standardisation Process by the algorithm designers:

  **Hongjun Wu** and **Tao Huang**

## Source

Downloaded from the NIST LWC Finalists page:

  https://csrc.nist.gov/Projects/lightweight-cryptography/finalists

Direct link to the submission zip:

  https://csrc.nist.gov/CSRC/media/Projects/lightweight-cryptography/
  documents/finalist-round/updated-submissions/tinyjambu.zip

The files in this directory are from:

  `tinyjambu/Implementations/crypto_aead/tinyjambu192v2/opt/`

This is the **optimized implementation for 32-bit processors** written by
Hongjun Wu.  It processes 128 NLFSR rounds per loop iteration (4× unrolled)
instead of 32 rounds in the reference version, yielding better performance
on the Cortex-A72.

## Specification

  https://csrc.nist.gov/CSRC/media/Projects/lightweight-cryptography/
  documents/finalist-round/updated-spec-doc/tinyjambu-spec-final.pdf

## Algorithm Parameters (TinyJambu-192)

| Parameter       | Value              |
|-----------------|--------------------|
| Key size        | 192 bits (24 bytes)|
| Nonce size      | 96 bits (12 bytes) |
| Tag size        | 64 bits (8 bytes)  |
| State size      | 128 bits           |
| Permutation     | NLFSR              |
| Round counts    | P₁₁₅₂ / P₆₄₀      |

## Files

* `api.h`        — SUPERCOP-compatible parameter definitions
* `crypto_aead.h`— Function prototype declarations for the SUPERCOP interface
* `encrypt.c`    — Optimized implementation by Hongjun Wu

## KAT Validation

Validated against all 1,089 Known Answer Test vectors from the official
NIST submission (`LWC_AEAD_KAT_192_96.txt`).

## License

The NIST LWC submission code is in the public domain.
