TinyJambu-192 AEAD — Pure C Reference Implementation
=====================================================

This directory contains a self-contained, pure-C implementation of the
TinyJambu-192 Authenticated Encryption with Associated Data (AEAD) scheme.

TinyJambu was designed by **Hongjun Wu** and **Tao Huang** and was one of 
the ten finalists of the NIST Lightweight Cryptography (LWC) standardisation
process (2019–2023).  The full specification is available from NIST:

  https://csrc.nist.gov/CSRC/media/Projects/lightweight-cryptography/
  documents/finalist-round/updated-spec-doc/tinyjambu-spec-final.pdf

The code here was ported from the CC0-licensed C++ header-only library by
**Anjan Roy** (https://github.com/itzmeanjan/tinyjambu), translating the
templated C++20 code into portable C99.  All algorithmic constants and
NLFSR round counts follow the specification exactly.

Files
-----
* ``tinyjambu192.c`` — single-file implementation (header + body).
  Included directly by ``core/_tinyjambu_native.c`` at compile time,
  following the same pattern used for the Ascon AEAD native extension.

License
-------
CC0-1.0 (public domain dedication), matching the upstream library.
