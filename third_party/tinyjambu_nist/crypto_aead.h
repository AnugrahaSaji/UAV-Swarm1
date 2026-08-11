/*
 * SUPERCOP crypto_aead.h — prototype declarations for TinyJambu AEAD.
 *
 * This header is required by the NIST LWC submission's encrypt.c which
 * #includes "crypto_aead.h" but the submission zip only ships api.h.
 * We bridge the gap here.
 */
#ifndef CRYPTO_AEAD_H
#define CRYPTO_AEAD_H

#include "api.h"

int crypto_aead_encrypt(
    unsigned char *c, unsigned long long *clen,
    const unsigned char *m, unsigned long long mlen,
    const unsigned char *ad, unsigned long long adlen,
    const unsigned char *nsec,
    const unsigned char *npub,
    const unsigned char *k);

int crypto_aead_decrypt(
    unsigned char *m, unsigned long long *mlen,
    unsigned char *nsec,
    const unsigned char *c, unsigned long long clen,
    const unsigned char *ad, unsigned long long adlen,
    const unsigned char *npub,
    const unsigned char *k);

#endif /* CRYPTO_AEAD_H */
