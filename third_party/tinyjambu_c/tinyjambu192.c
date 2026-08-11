/*
 * TinyJambu-192 Authenticated Encryption with Associated Data
 * Pure C reference implementation
 *
 * Based on the NIST LWC finalist specification by Hongjun Wu & Tao Huang:
 *   https://csrc.nist.gov/CSRC/media/Projects/lightweight-cryptography/
 *   documents/finalist-round/updated-spec-doc/tinyjambu-spec-final.pdf
 *
 * Algorithm summary (TinyJambu-192):
 *   - 128-bit NLFSR permutation state
 *   - 192-bit secret key  (24 bytes, 6 x 32-bit words)
 *   - 96-bit  nonce       (12 bytes, 3 x 32-bit words)
 *   - 64-bit  auth tag    ( 8 bytes, 2 x 32-bit words)
 *   - Feedback polynomial: fb = s0 ^ s47 ^ (~(s70 & s85)) ^ s91 ^ k_{i mod 6}
 *
 * Round counts for TinyJambu-192:
 *   P_{1152} = 1152 NLFSR clocks  (key setup, CT processing, 1st finalize)
 *   P_{640}  =  640 NLFSR clocks  (nonce setup, AD processing, 2nd finalize)
 *
 * Framebits (3-bit, left-shifted by 4 to align with state bits 36-38):
 *   Nonce = 0x10,  AD = 0x30,  CT = 0x50,  Tag = 0x70
 *
 * This code is placed in the public domain (CC0-1.0).
 * Ported from the itzmeanjan/tinyjambu C++ header-only library (also CC0-1.0),
 * which itself follows the above NIST specification.
 *
 * Reference repo: https://github.com/itzmeanjan/tinyjambu
 */

#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* ── Constants ──────────────────────────────────────────────────────────── */

#define TJ192_KEY_BYTES    24
#define TJ192_NONCE_BYTES  12
#define TJ192_TAG_BYTES     8

#define FRAMEBITS_NONCE  0x10u   /* 1 << 4 */
#define FRAMEBITS_AD     0x30u   /* 3 << 4 */
#define FRAMEBITS_CT     0x50u   /* 5 << 4 */
#define FRAMEBITS_TAG    0x70u   /* 7 << 4 */

/* ── Little-endian helpers ──────────────────────────────────────────────── */

static inline uint32_t
tj_load_le32(const uint8_t *p)
{
    return (uint32_t)p[0]        |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16)|
           ((uint32_t)p[3] << 24);
}

static inline void
tj_store_le32(uint8_t *p, uint32_t w)
{
    p[0] = (uint8_t)(w);
    p[1] = (uint8_t)(w >> 8);
    p[2] = (uint8_t)(w >> 16);
    p[3] = (uint8_t)(w >> 24);
}

/* ── StateUpdate-192 ────────────────────────────────────────────────────── */
/*
 * NLFSR feedback (32 bits per iteration):
 *   fb = s[0] ^ s[47] ^ (~(s[70] & s[85])) ^ s[91] ^ key[i % 6]
 *
 * where s[n] denotes bit n of the 128-bit state stored as 4 x uint32_t:
 *   s[ 47] → (state[1] >> 15) | (state[2] << 17)   — but we want a full word
 *   s[ 70] → (state[2] >>  6) | (state[3] << 26)
 *   s[ 85] → (state[2] >> 21) | (state[3] << 11)
 *   s[ 91] → (state[2] >> 27) | (state[3] <<  5)
 *
 * After computing the 32-bit feedback word, the state shifts left by one word.
 */
static void
tj192_state_update(uint32_t state[4], const uint32_t key[6], size_t rounds)
{
    size_t itr = rounds >> 5;   /* rounds / 32 */
    size_t i;
    for (i = 0; i < itr; i++) {
        size_t j = i % 6u;
        uint32_t s47 = (state[2] << 17) | (state[1] >> 15);
        uint32_t s70 = (state[3] << 26) | (state[2] >>  6);
        uint32_t s85 = (state[3] << 11) | (state[2] >> 21);
        uint32_t s91 = (state[3] <<  5) | (state[2] >> 27);

        uint32_t fbk = state[0] ^ s47 ^ (~(s70 & s85)) ^ s91 ^ key[j];

        state[0] = state[1];
        state[1] = state[2];
        state[2] = state[3];
        state[3] = fbk;
    }
}

/* ── Initialization ─────────────────────────────────────────────────────── */

static void
tj192_initialize(uint32_t state[4], const uint32_t key[6], const uint8_t *nonce)
{
    size_t i;
    /* Zero the 128-bit state */
    memset(state, 0, 16);

    /* Key setup: P_{1152} */
    tj192_state_update(state, key, 1152);

    /* Nonce setup: 3 words, each with P_{640} */
    for (i = 0; i < 3; i++) {
        state[1] ^= FRAMEBITS_NONCE;
        tj192_state_update(state, key, 640);
        state[3] ^= tj_load_le32(nonce + i * 4);
    }
}

/* ── Process Associated Data ────────────────────────────────────────────── */

static void
tj192_process_ad(uint32_t state[4], const uint32_t key[6],
                 const uint8_t *ad, size_t ad_len)
{
    size_t partial = ad_len & 3u;
    size_t off = 0;

    while (off < ad_len) {
        state[1] ^= FRAMEBITS_AD;
        tj192_state_update(state, key, 640);

        size_t take = ad_len - off;
        if (take > 4) take = 4;

        uint32_t word = 0;
        size_t b;
        for (b = 0; b < take; b++)
            word |= (uint32_t)ad[off + b] << (b * 8);

        state[3] ^= word;
        off += take;
    }

    state[1] ^= (uint32_t)partial;
}

/* ── Process Plain Text (encrypt) ───────────────────────────────────────── */

static void
tj192_process_pt(uint32_t state[4], const uint32_t key[6],
                 const uint8_t *pt, uint8_t *ct, size_t len)
{
    size_t partial = len & 3u;
    size_t off = 0;

    while (off < len) {
        state[1] ^= FRAMEBITS_CT;
        tj192_state_update(state, key, 1152);

        size_t take = len - off;
        if (take > 4) take = 4;

        uint32_t word = 0;
        size_t b;
        for (b = 0; b < take; b++)
            word |= (uint32_t)pt[off + b] << (b * 8);

        state[3] ^= word;
        uint32_t enc = state[2] ^ word;

        for (b = 0; b < take; b++)
            ct[off + b] = (uint8_t)(enc >> (b * 8));

        off += take;
    }

    state[1] ^= (uint32_t)partial;
}

/* ── Process Cipher Text (decrypt) ──────────────────────────────────────── */

static void
tj192_process_ct(uint32_t state[4], const uint32_t key[6],
                 const uint8_t *ct, uint8_t *pt, size_t len)
{
    size_t partial = len & 3u;
    size_t off = 0;

    while (off < len) {
        state[1] ^= FRAMEBITS_CT;
        tj192_state_update(state, key, 1152);

        size_t take = len - off;
        if (take > 4) take = 4;

        uint32_t word = 0;
        size_t b;
        for (b = 0; b < take; b++)
            word |= (uint32_t)ct[off + b] << (b * 8);

        uint32_t dec = state[2] ^ word;
        uint32_t mask = 0xffffffffu >> ((4u - take) * 8);
        state[3] ^= (dec & mask);

        for (b = 0; b < take; b++)
            pt[off + b] = (uint8_t)(dec >> (b * 8));

        off += take;
    }

    state[1] ^= (uint32_t)partial;
}

/* ── Finalization ───────────────────────────────────────────────────────── */

static void
tj192_finalize(uint32_t state[4], const uint32_t key[6], uint8_t *tag)
{
    /* First tag word: P_{1152} */
    state[1] ^= FRAMEBITS_TAG;
    tj192_state_update(state, key, 1152);
    tj_store_le32(tag, state[2]);

    /* Second tag word: P_{640} */
    state[1] ^= FRAMEBITS_TAG;
    tj192_state_update(state, key, 640);
    tj_store_le32(tag + 4, state[2]);
}

/* ── Public API ─────────────────────────────────────────────────────────── */

/*
 * tj192_aead_encrypt
 *   Encrypt plaintext and produce ciphertext + 8-byte authentication tag.
 *   ct must have room for pt_len bytes, tag must have room for 8 bytes.
 *   Returns 0 on success.
 */
static int
tj192_aead_encrypt(const uint8_t *key,   /* 24 bytes */
                   const uint8_t *nonce, /* 12 bytes */
                   const uint8_t *ad,    size_t ad_len,
                   const uint8_t *pt,    size_t pt_len,
                   uint8_t       *ct,    uint8_t *tag)
{
    uint32_t state[4];
    uint32_t key_w[6];
    int i;

    for (i = 0; i < 6; i++)
        key_w[i] = tj_load_le32(key + i * 4);

    tj192_initialize(state, key_w, nonce);
    tj192_process_ad(state, key_w, ad, ad_len);
    tj192_process_pt(state, key_w, pt, ct, pt_len);
    tj192_finalize(state, key_w, tag);

    /* Zeroize sensitive material */
    memset(state, 0, sizeof(state));
    memset(key_w, 0, sizeof(key_w));
    return 0;
}

/*
 * tj192_aead_decrypt
 *   Decrypt ciphertext and verify the 8-byte authentication tag.
 *   pt must have room for ct_len bytes.
 *   Returns 0 on success (tag verified), -1 on failure (pt is zeroed).
 */
static int
tj192_aead_decrypt(const uint8_t *key,   /* 24 bytes */
                   const uint8_t *nonce, /* 12 bytes */
                   const uint8_t *ad,    size_t ad_len,
                   const uint8_t *ct,    size_t ct_len,
                   uint8_t       *pt,    const uint8_t *tag)
{
    uint32_t state[4];
    uint32_t key_w[6];
    uint8_t  computed_tag[TJ192_TAG_BYTES];
    int i;
    uint8_t diff;

    for (i = 0; i < 6; i++)
        key_w[i] = tj_load_le32(key + i * 4);

    tj192_initialize(state, key_w, nonce);
    tj192_process_ad(state, key_w, ad, ad_len);
    tj192_process_ct(state, key_w, ct, pt, ct_len);
    tj192_finalize(state, key_w, computed_tag);

    /* Constant-time tag comparison */
    diff = 0;
    for (i = 0; i < TJ192_TAG_BYTES; i++)
        diff |= tag[i] ^ computed_tag[i];

    /* Release-of-Unverified-Plaintext (RUP) protection */
    if (diff != 0)
        memset(pt, 0, ct_len);

    /* Zeroize sensitive material */
    memset(state, 0, sizeof(state));
    memset(key_w, 0, sizeof(key_w));
    memset(computed_tag, 0, sizeof(computed_tag));

    return (diff == 0) ? 0 : -1;
}
