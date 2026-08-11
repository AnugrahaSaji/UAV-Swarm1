#!/usr/bin/env python3
"""
Pi5 vs Pi4 benchmark comparison table.

Reads comprehensive JSONs from both Pi5 and Pi4 runs (no-ddos baseline),
computes per-suite metrics, and produces a comparison markdown table.
"""
import json, os, sys
from pathlib import Path
from collections import defaultdict

PI5_RUN = Path("logs/benchmarks/runs/pi5_full_20260223_1808/no-ddos")
PI4_RUN = Path("logs/benchmarks/runs/20260220_full/no-ddos")

def load_drone_jsons(run_dir: Path) -> dict:
    """Load all *_drone.json files, keyed by canonical suite name."""
    suites = {}
    for f in sorted(run_dir.glob("*_drone.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        ci = d.get("crypto_identity", {})
        kem = ci.get("kem_algorithm", "?")
        aead = ci.get("aead_algorithm", "?")
        sig = ci.get("sig_algorithm", "?")
        # Build canonical key from filename
        name = f.stem  # e.g. 20260223_123822_cs-mlkem512-aesgcm-falcon512_drone
        parts = name.split("_")
        # Find the cs- part
        suite_key = None
        for p in parts:
            if p.startswith("cs-"):
                suite_key = p
                break
        if not suite_key:
            # Try joining parts between timestamp and _drone
            idx = 2 if len(parts) > 3 else 0
            suite_key = "_".join(parts[idx:-1])
        
        if suite_key == "unknown":
            continue
            
        suites[suite_key] = d
    return suites


def extract_metrics(d: dict) -> dict:
    """Extract the key comparison metrics from a comprehensive JSON."""
    hs = d.get("handshake", {})
    pe = d.get("power_energy", {})
    dp = d.get("data_plane", {})
    ci = d.get("crypto_identity", {})
    lj = d.get("latency_jitter", {})
    sd = d.get("system_drone", {})
    
    return {
        "kem": ci.get("kem_algorithm", "?"),
        "aead": ci.get("aead_algorithm", "?"),
        "sig": ci.get("sig_algorithm", "?"),
        "kem_family": ci.get("kem_family", "?"),
        "level": ci.get("suite_security_level", "?"),
        "handshake_ms": hs.get("handshake_total_duration_ms") or hs.get("protocol_handshake_duration_ms"),
        "power_avg_w": pe.get("power_avg_w"),
        "power_peak_w": pe.get("power_peak_w"),
        "energy_total_j": pe.get("energy_total_j"),
        "ptx_in": dp.get("ptx_in"),
        "enc_out": dp.get("enc_out"),
        "power_sensor": pe.get("power_sensor_type", "?"),
        "cpu_avg": sd.get("cpu_percent_avg"),
        "mem_avg_mb": sd.get("memory_rss_mb_avg"),
    }


def fmt(val, decimals=2, suffix=""):
    if val is None:
        return "—"
    if isinstance(val, float):
        return f"{val:.{decimals}f}{suffix}"
    return f"{val}{suffix}"


def main():
    if not PI5_RUN.exists():
        print(f"ERROR: Pi5 data not found at {PI5_RUN}")
        sys.exit(1)
    if not PI4_RUN.exists():
        print(f"ERROR: Pi4 data not found at {PI4_RUN}")
        sys.exit(1)

    pi5 = load_drone_jsons(PI5_RUN)
    pi4 = load_drone_jsons(PI4_RUN)
    
    print(f"Pi5 suites: {len(pi5)}")
    print(f"Pi4 suites: {len(pi4)}")
    
    # Find common suites
    common = sorted(set(pi5.keys()) & set(pi4.keys()))
    pi5_only = sorted(set(pi5.keys()) - set(pi4.keys()))
    pi4_only = sorted(set(pi4.keys()) - set(pi5.keys()))
    
    print(f"Common: {len(common)}, Pi5-only: {len(pi5_only)}, Pi4-only: {len(pi4_only)}")
    
    if pi5_only:
        print(f"\nPi5-only suites (not in Pi4 data): {pi5_only[:10]}")
    if pi4_only:
        print(f"\nPi4-only suites: {pi4_only[:10]}")
    
    # Build comparison table
    rows = []
    for sk in common:
        m5 = extract_metrics(pi5[sk])
        m4 = extract_metrics(pi4[sk])
        
        hs5 = m5["handshake_ms"]
        hs4 = m4["handshake_ms"]
        speedup = (hs4 / hs5) if (hs5 and hs4 and hs5 > 0) else None
        
        pw5 = m5["power_avg_w"]
        pw4 = m4["power_avg_w"]
        
        en5 = m5["energy_total_j"]
        en4 = m4["energy_total_j"]
        
        rows.append({
            "suite": sk.replace("cs-", ""),
            "kem": m5["kem"],
            "aead": m5["aead"],
            "sig": m5["sig"],
            "level": m5["level"],
            "hs_pi5": hs5,
            "hs_pi4": hs4,
            "speedup": speedup,
            "pw_pi5": pw5,
            "pw_pi4": pw4,
            "en_pi5": en5,
            "en_pi4": en4,
            "ptx_pi5": m5["ptx_in"],
            "ptx_pi4": m4["ptx_in"],
        })
    
    # Sort by KEM family, then security level, then AEAD, then sig
    def sort_key(r):
        kem_order = {"ML-KEM": 0, "HQC": 1, "Classic-McEliece": 2, "BIKE": 3, "FrodoKEM": 4}
        kem_fam = r["kem"].split("-")[0] if "-" in r["kem"] else r["kem"]
        for k, v in kem_order.items():
            if k in r["kem"]:
                return (v, r["level"], r["aead"], r["sig"])
        return (9, r["level"], r["aead"], r["sig"])
    
    rows.sort(key=sort_key)
    
    # Print markdown table
    print("\n" + "=" * 120)
    print("## Pi5 vs Pi4 — Baseline (no-ddos) Comparison")
    print("=" * 120)
    print()
    
    # Summary table by KEM family
    print("### Per-KEM Family Summary")
    print()
    print("| KEM Family | #Suites | Handshake Pi5 (ms) | Handshake Pi4 (ms) | Speedup | Power Pi5 (W) | Power Pi4 (W) | Energy Pi5 (J) | Energy Pi4 (J) |")
    print("|---|---|---|---|---|---|---|---|---|")
    
    fam_data = defaultdict(lambda: {"count": 0, "hs5": [], "hs4": [], "pw5": [], "pw4": [], "en5": [], "en4": []})
    for r in rows:
        kem = r["kem"]
        for fam_name in ["ML-KEM", "HQC", "Classic-McEliece", "BIKE", "FrodoKEM"]:
            if fam_name in kem:
                fd = fam_data[fam_name]
                break
        else:
            fd = fam_data[kem]
        
        fd["count"] += 1
        if r["hs_pi5"] is not None: fd["hs5"].append(r["hs_pi5"])
        if r["hs_pi4"] is not None: fd["hs4"].append(r["hs_pi4"])
        if r["pw_pi5"] is not None: fd["pw5"].append(r["pw_pi5"])
        if r["pw_pi4"] is not None: fd["pw4"].append(r["pw_pi4"])
        if r["en_pi5"] is not None: fd["en5"].append(r["en_pi5"])
        if r["en_pi4"] is not None: fd["en4"].append(r["en_pi4"])
    
    for fam in ["ML-KEM", "HQC", "Classic-McEliece"]:
        fd = fam_data.get(fam)
        if not fd or fd["count"] == 0:
            continue
        avg_hs5 = sum(fd["hs5"]) / len(fd["hs5"]) if fd["hs5"] else None
        avg_hs4 = sum(fd["hs4"]) / len(fd["hs4"]) if fd["hs4"] else None
        sp = (avg_hs4 / avg_hs5) if (avg_hs5 and avg_hs4 and avg_hs5 > 0) else None
        avg_pw5 = sum(fd["pw5"]) / len(fd["pw5"]) if fd["pw5"] else None
        avg_pw4 = sum(fd["pw4"]) / len(fd["pw4"]) if fd["pw4"] else None
        avg_en5 = sum(fd["en5"]) / len(fd["en5"]) if fd["en5"] else None
        avg_en4 = sum(fd["en4"]) / len(fd["en4"]) if fd["en4"] else None
        
        print(f"| {fam} | {fd['count']} | {fmt(avg_hs5, 1)} | {fmt(avg_hs4, 1)} | {fmt(sp, 2, 'x')} | {fmt(avg_pw5, 2)} | {fmt(avg_pw4, 2)} | {fmt(avg_en5, 1)} | {fmt(avg_en4, 1)} |")
    
    # Detailed per-suite table
    print()
    print("### Detailed Per-Suite Comparison")
    print()
    print("| Suite | Level | Handshake Pi5 (ms) | Handshake Pi4 (ms) | Speedup | Power Pi5 (W) | Power Pi4 (W) | Energy Pi5 (J) | Energy Pi4 (J) | MAV pkts Pi5 | MAV pkts Pi4 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    
    for r in rows:
        suite_short = r["suite"]
        # Shorten names
        suite_short = suite_short.replace("classicmceliece", "mce")
        suite_short = suite_short.replace("chacha20poly1305", "chacha")
        suite_short = suite_short.replace("sphincs", "sph")
        
        sp = fmt(r["speedup"], 2, "x") if r["speedup"] else "—"
        
        print(f"| {suite_short} | {r['level']} | {fmt(r['hs_pi5'], 1)} | {fmt(r['hs_pi4'], 1)} | {sp} | {fmt(r['pw_pi5'], 2)} | {fmt(r['pw_pi4'], 2)} | {fmt(r['en_pi5'], 1)} | {fmt(r['en_pi4'], 1)} | {r['ptx_pi5'] or '—'} | {r['ptx_pi4'] or '—'} |")
    
    # Pi5-only suites (HQC, etc.)
    if pi5_only:
        print()
        print("### Pi5-Only Suites (no Pi4 data)")
        print()
        print("| Suite | Level | Handshake (ms) | Power (W) | Energy (J) | MAV pkts |")
        print("|---|---|---|---|---|---|")
        for sk in pi5_only:
            m = extract_metrics(pi5[sk])
            suite_short = sk.replace("cs-", "").replace("classicmceliece", "mce").replace("chacha20poly1305", "chacha").replace("sphincs", "sph")
            print(f"| {suite_short} | {m['level']} | {fmt(m['handshake_ms'], 1)} | {fmt(m['power_avg_w'], 2)} | {fmt(m['energy_total_j'], 1)} | {m['ptx_in'] or '—'} |")
    
    # Overall summary
    print()
    print("### Overall Summary")
    print()
    all_sp = [r["speedup"] for r in rows if r["speedup"]]
    if all_sp:
        print(f"- **Average handshake speedup (Pi5/Pi4)**: {sum(all_sp)/len(all_sp):.2f}x")
        print(f"- **Min speedup**: {min(all_sp):.2f}x")
        print(f"- **Max speedup**: {max(all_sp):.2f}x")
    
    all_pw5 = [r["pw_pi5"] for r in rows if r["pw_pi5"]]
    all_pw4 = [r["pw_pi4"] for r in rows if r["pw_pi4"]]
    if all_pw5 and all_pw4:
        avg5 = sum(all_pw5) / len(all_pw5)
        avg4 = sum(all_pw4) / len(all_pw4)
        print(f"- **Average power**: Pi5={avg5:.2f}W, Pi4={avg4:.2f}W")
        print(f"- **Power ratio (Pi5/Pi4)**: {avg5/avg4:.2f}x")
    
    all_en5 = [r["en_pi5"] for r in rows if r["en_pi5"]]
    all_en4 = [r["en_pi4"] for r in rows if r["en_pi4"]]
    if all_en5 and all_en4:
        avg5 = sum(all_en5) / len(all_en5)
        avg4 = sum(all_en4) / len(all_en4)
        print(f"- **Average energy per suite**: Pi5={avg5:.1f}J, Pi4={avg4:.1f}J")
        
    # Power sensor info
    print()
    print("### Measurement Details")
    print("- **Pi5**: Raspberry Pi 5 (BCM2712, 4-core Cortex-A76 @ 2.4GHz)")
    print("  - Power: PMIC (`vcgencmd pmic_read_adc`) — 12 current + 14 voltage rails")
    print("  - liboqs: 0.14.1-dev (rebuilt with HQC)")
    print("  - Python: 3.13.5, ascon 0.0.9")
    print("- **Pi4**: Raspberry Pi 4 Model B (BCM2711, 4-core Cortex-A72 @ 1.5GHz)")
    print("  - Power: INA219 I2C shunt sensor")
    print("  - liboqs: 0.14.0")
    print("  - Python: 3.11.2")
    print(f"- **Test config**: 10s per suite, MAVProxy mode, real Pixhawk FC")
    print(f"- **Pi5 suites total**: {len(pi5)} (including HQC-128/192/256)")
    print(f"- **Pi4 suites total**: {len(pi4)}")
    print(f"- **Common suites compared**: {len(common)}")


if __name__ == "__main__":
    main()
