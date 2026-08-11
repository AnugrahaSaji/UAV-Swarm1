#!/usr/bin/env python3
"""Download all reference papers for the secure-tunnel paper."""
import urllib.request, os, ssl, sys, json
from concurrent.futures import ThreadPoolExecutor, as_completed

ctx = ssl.create_default_context()
OUTDIR = os.path.dirname(os.path.abspath(__file__))

# ── Mapping: filename → URL ──
# Only freely-accessible sources (NIST, RFCs, IACR ePrint, arXiv, open specs)
URLS = {
    # NIST FIPS Standards
    "01_NIST_FIPS_203_ML-KEM.pdf":
        "https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf",
    "02_NIST_FIPS_204_ML-DSA.pdf":
        "https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf",
    "03_NIST_FIPS_205_SLH-DSA.pdf":
        "https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.205.pdf",
    "04_NIST_IR_8545_Round4.pdf":
        "https://nvlpubs.nist.gov/nistpubs/ir/2024/NIST.IR.8545.pdf",
    "05_NIST_SP800-131A_Rev2.pdf":
        "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-131Ar2.pdf",

    # PQC Algorithm Papers (IACR ePrint / NIST submissions)
    "06_Kyber_CRYSTALS.pdf":
        "https://eprint.iacr.org/2017/634.pdf",
    "07_Dilithium_CRYSTALS.pdf":
        "https://eprint.iacr.org/2017/633.pdf",
    "08_Falcon_Specification.pdf":
        "https://falcon-sign.info/falcon.pdf",
    "09_SPHINCSplus_Framework.pdf":
        "https://eprint.iacr.org/2019/1452.pdf",
    "10_HQC_Specification.pdf":
        "https://eprint.iacr.org/2017/1005.pdf",
    "11_ClassicMcEliece.pdf":
        "https://eprint.iacr.org/2022/232.pdf",
    "12_Ascon_Lightweight.pdf":
        "https://eprint.iacr.org/2019/1468.pdf",

    # RFCs
    "13_RFC5869_HKDF.pdf":
        "https://www.rfc-editor.org/rfc/pdfrfc/rfc5869.txt.pdf",
    "14_RFC8439_ChaCha20_Poly1305.pdf":
        "https://www.rfc-editor.org/rfc/pdfrfc/rfc8439.txt.pdf",
    "15_RFC5288_AES_GCM_TLS.pdf":
        "https://www.rfc-editor.org/rfc/pdfrfc/rfc5288.txt.pdf",
    "16_RFC2104_HMAC.pdf":
        "https://www.rfc-editor.org/rfc/pdfrfc/rfc2104.txt.pdf",

    # Foundational CS (arXiv)
    "17_Shor1994_QuantumAlgorithm.pdf":
        "https://arxiv.org/pdf/quant-ph/9508027",
    "18_Grover1996_Search.pdf":
        "https://arxiv.org/pdf/quant-ph/9605043",

    # PQC Benchmarks (IACR ePrint)
    "19_pqm4_ARM_Cortex_M4.pdf":
        "https://eprint.iacr.org/2019/844.pdf",
    "20_PQC_TLS_Benchmarking.pdf":
        "https://eprint.iacr.org/2019/1447.pdf",

    # PQC VPN / Rosenpass
    "21_Rosenpass_PQC_VPN.pdf":
        "https://eprint.iacr.org/2024/905.pdf",
}

# References that are web-only (no direct PDF download possible):
#   liboqs, oqspython, cryptography-lib, mavlink-spec, mavproxy,
#   ardupilot, pixhawk → documentation/GitHub pages
# References behind paywalls (IEEE/ACM):
#   dolev1983security, drone-security-survey, drone-pqc-analysis,
#   pqc-arm-bench, pqc-vpn, cicids2017, tst-ids
# Hardware datasheet:
#   ina219 → TI datasheet

PAYWALL_OR_WEB = {
    "dolev1983security": "IEEE Trans. (paywall) — Dolev-Yao model",
    "drone-security-survey": "ACM Trans. (paywall) — Altawy & Youssef 2017",
    "drone-pqc-analysis": "IEEE ICC (paywall) — Pham & Vakilinia 2023",
    "pqc-arm-bench": "DATE 2023 (paywall) — Schmid et al.",
    "pqc-vpn": "IEEE S&P (paywall) — Hülsing et al. 2021",
    "cicids2017": "ICISSP (paywall/limited) — Sharafaldin et al. 2018",
    "tst-ids": "IEEE TIFS (paywall) — Zhang et al. 2023",
    "liboqs": "Web: https://openquantumsafe.org",
    "oqspython": "Web: https://github.com/open-quantum-safe/liboqs-python",
    "cryptography-lib": "Web: https://cryptography.io",
    "mavlink-spec": "Web: https://mavlink.io/en/",
    "mavproxy": "Web: https://ardupilot.github.io/MAVProxy/",
    "ardupilot": "Web: https://ardupilot.org",
    "pixhawk": "Web: https://holybro.com/products/pixhawk-6c-mini",
    "ina219": "TI Datasheet SBOS448G",
}


def download(fname_url):
    fname, url = fname_url
    fpath = os.path.join(OUTDIR, fname)
    if os.path.exists(fpath) and os.path.getsize(fpath) > 5000:
        return ("SKIP", fname, os.path.getsize(fpath))
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp = urllib.request.urlopen(req, context=ctx, timeout=45)
        data = resp.read()
        if len(data) < 1000:
            return ("TINY", fname, len(data))
        with open(fpath, "wb") as f:
            f.write(data)
        return ("OK", fname, len(data))
    except Exception as e:
        return ("FAIL", fname, str(e))


if __name__ == "__main__":
    print(f"Downloading {len(URLS)} references to {OUTDIR}\n")
    results = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(download, item): item[0] for item in URLS.items()}
        for fut in as_completed(futures):
            status, fname, info = fut.result()
            tag = f"[{status}]"
            if status == "OK":
                print(f"  {tag:6s} {fname} ({info:,} bytes)")
            elif status == "SKIP":
                print(f"  {tag:6s} {fname} (exists, {info:,} bytes)")
            else:
                print(f"  {tag:6s} {fname} — {info}")
            results.append((status, fname, info))

    print(f"\n{'='*60}")
    ok = sum(1 for s, _, _ in results if s in ("OK", "SKIP"))
    fail = sum(1 for s, _, _ in results if s == "FAIL")
    tiny = sum(1 for s, _, _ in results if s == "TINY")
    print(f"Downloaded: {ok}  |  Failed: {fail}  |  Too small: {tiny}")

    print(f"\nPaywall/web-only references ({len(PAYWALL_OR_WEB)}):")
    for key, desc in PAYWALL_OR_WEB.items():
        print(f"  • {key}: {desc}")
    print(f"\nTotal coverage: {ok}/{ok + fail + tiny + len(PAYWALL_OR_WEB)} references")
