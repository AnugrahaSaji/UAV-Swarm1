#!/usr/bin/env python3
"""Comprehensive AEAD analysis for policy design."""
import json, os, glob
from collections import defaultdict

aead_dir = "individual_benchmarks/raw_data/5iter_test/raw/aead"
results = []

for f in sorted(glob.glob(os.path.join(aead_dir, "*.json"))):
    name = os.path.basename(f)
    with open(f) as fh:
        d = json.load(fh)
    
    algo = d["algorithm"]
    op = d["operation"]
    size = d["payload_size"]
    
    # Timing (ns)
    wall_ns = d["timing"]["wall_ns"]
    avg_ns = sum(wall_ns) / len(wall_ns)
    
    # Power
    power = d.get("power", {})
    power_means = power.get("power_mean_w", [])
    energy_j = power.get("energy_j", [])
    voltage_v = power.get("voltage_mean_v", [])
    current_a = power.get("current_mean_a", [])
    
    avg_power = sum(power_means) / len(power_means) if power_means else None
    avg_energy = sum(energy_j) / len(energy_j) if energy_j else None
    avg_voltage = sum(voltage_v) / len(voltage_v) if voltage_v else None
    avg_current = sum(current_a) / len(current_a) if current_a else None
    
    # Energy per operation (nJ)
    energy_per_op_nj = (avg_energy * 1e9) if avg_energy else None
    
    results.append({
        "algo": algo, "op": op, "size": size,
        "time_ns": avg_ns, "power_w": avg_power,
        "energy_per_op_nj": energy_per_op_nj,
        "voltage_v": avg_voltage, "current_a": avg_current,
    })

# Print formatted table
print("=" * 100)
print(f"{'Algorithm':<20} {'Op':<10} {'Size':>6} {'Time(us)':>10} {'Power(W)':>10} {'Energy/op(uJ)':>14} {'V':>6} {'A':>6}")
print("=" * 100)

for r in sorted(results, key=lambda x: (x["algo"], x["op"], x["size"])):
    time_us = r["time_ns"] / 1000
    energy_uj = r["energy_per_op_nj"] / 1000 if r["energy_per_op_nj"] else 0
    print(f"{r['algo']:<20} {r['op']:<10} {r['size']:>6}B {time_us:>9.1f} {r['power_w'] or 0:>10.3f} {energy_uj:>14.3f} {r['voltage_v'] or 0:>5.2f} {r['current_a'] or 0:>5.3f}")

# Summary by algorithm
print("\n" + "=" * 80)
print("SUMMARY BY ALGORITHM")
print("=" * 80)

algo_summary = defaultdict(lambda: {"enc_ns": [], "dec_ns": [], "enc_power": [], "dec_power": [], "enc_energy": [], "dec_energy": []})
for r in results:
    key = r["algo"]
    if r["op"] == "encrypt":
        algo_summary[key]["enc_ns"].append(r["time_ns"])
        if r["power_w"]: algo_summary[key]["enc_power"].append(r["power_w"])
        if r["energy_per_op_nj"]: algo_summary[key]["enc_energy"].append(r["energy_per_op_nj"])
    else:
        algo_summary[key]["dec_ns"].append(r["time_ns"])
        if r["power_w"]: algo_summary[key]["dec_power"].append(r["power_w"])
        if r["energy_per_op_nj"]: algo_summary[key]["dec_energy"].append(r["energy_per_op_nj"])

for algo in sorted(algo_summary.keys()):
    s = algo_summary[algo]
    avg_enc = sum(s["enc_ns"]) / len(s["enc_ns"]) / 1000 if s["enc_ns"] else 0
    avg_dec = sum(s["dec_ns"]) / len(s["dec_ns"]) / 1000 if s["dec_ns"] else 0
    avg_enc_pw = sum(s["enc_power"]) / len(s["enc_power"]) if s["enc_power"] else 0
    avg_dec_pw = sum(s["dec_power"]) / len(s["dec_power"]) if s["dec_power"] else 0
    avg_enc_energy = sum(s["enc_energy"]) / len(s["enc_energy"]) / 1000 if s["enc_energy"] else 0
    avg_dec_energy = sum(s["dec_energy"]) / len(s["dec_energy"]) / 1000 if s["dec_energy"] else 0
    
    print(f"\n{algo}:")
    print(f"  Encrypt: {avg_enc:.1f} us avg, {avg_enc_pw:.3f} W, {avg_enc_energy:.3f} uJ/op")
    print(f"  Decrypt: {avg_dec:.1f} us avg, {avg_dec_pw:.3f} W, {avg_dec_energy:.3f} uJ/op")
    
    # Cost ratio relative to ChaCha20
    if algo != "ChaCha20-Poly1305":
        chacha = algo_summary.get("ChaCha20-Poly1305", {})
        if chacha.get("enc_ns"):
            chacha_enc = sum(chacha["enc_ns"]) / len(chacha["enc_ns"])
            ratio_enc = (sum(s["enc_ns"]) / len(s["enc_ns"])) / chacha_enc if s["enc_ns"] else 0
            chacha_dec = sum(chacha["dec_ns"]) / len(chacha["dec_ns"])
            ratio_dec = (sum(s["dec_ns"]) / len(s["dec_ns"])) / chacha_dec if s["dec_ns"] else 0
            print(f"  vs ChaCha20: encrypt {ratio_enc:.1f}x, decrypt {ratio_dec:.1f}x")

# Also load suite-level encrypt/decrypt ns from actual tunnel runs
print("\n" + "=" * 80)
print("SUITE LEVEL AEAD TIMINGS (actual tunnel runs)")
print("=" * 80)

suite_dirs = [
    "logs/benchmarks/runs/20260219/no-ddos",
    "logs/benchmarks/runs/20260219/ddos-xgboost",
]
for sd in suite_dirs:
    if not os.path.isdir(sd):
        continue
    print(f"\n--- {os.path.basename(sd)} ---")
    aead_enc = defaultdict(list)
    aead_dec = defaultdict(list)
    aead_temp = defaultdict(list)
    for f in sorted(os.listdir(sd)):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(sd, f)) as fh:
            try:
                d = json.load(fh)
            except:
                continue
        aead = d.get("crypto_identity", {}).get("aead_algorithm", "")
        dp = d.get("data_plane", {})
        sys_d = d.get("system_drone", {})
        enc = dp.get("aead_encrypt_avg_ns")
        dec = dp.get("aead_decrypt_avg_ns")
        temp = sys_d.get("temperature_c")
        if aead and enc:
            aead_enc[aead].append(enc)
        if aead and dec:
            aead_dec[aead].append(dec)
        if aead and temp:
            aead_temp[aead].append(temp)
    
    for aead in sorted(set(list(aead_enc.keys()) + list(aead_dec.keys()))):
        enc = aead_enc.get(aead, [])
        dec = aead_dec.get(aead, [])
        temp = aead_temp.get(aead, [])
        enc_avg = sum(enc) / len(enc) / 1000 if enc else 0
        dec_avg = sum(dec) / len(dec) / 1000 if dec else 0
        temp_avg = sum(temp) / len(temp) if temp else 0
        print(f"  {aead:<25} enc={enc_avg:>8.1f}us dec={dec_avg:>8.1f}us temp={temp_avg:.1f}C n={len(enc)}")
