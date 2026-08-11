/*
 * Standalone Ascon-AEAD128 shared library using the official NIST
 * SP 800-232 implementation from ascon/ascon-c.
 *
 * Source:
 *   third_party/ascon_c_sp800_232/crypto_aead/asconaead128/opt64
 *
 * Build with:
 *   python -m core.build_ascon_aead128
 *
 * Exported ABI:
 *   asconaead128_encrypt(tag, ct, msg, mlen, ad, adlen, nonce, key) -> 0
 *   asconaead128_decrypt(pt, tag, ct, ctlen, ad, adlen, nonce, key) -> 0/-1
 */

#include <stdint.h>

#include "../third_party/ascon_c_sp800_232/crypto_aead/asconaead128/opt64/aead.c"

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

EXPORT int asconaead128_encrypt(
    uint8_t* tag,
    uint8_t* ct,
    const uint8_t* msg,
    uint64_t mlen,
    const uint8_t* ad,
    uint64_t adlen,
    const uint8_t* nonce,
    const uint8_t* key) {
  return ascon_aead_encrypt(tag, ct, msg, mlen, ad, adlen, nonce, key);
}

EXPORT int asconaead128_decrypt(
    uint8_t* pt,
    const uint8_t* tag,
    const uint8_t* ct,
    uint64_t ctlen,
    const uint8_t* ad,
    uint64_t adlen,
    const uint8_t* nonce,
    const uint8_t* key) {
  return ascon_aead_decrypt(pt, tag, ct, ctlen, ad, adlen, nonce, key);
}
