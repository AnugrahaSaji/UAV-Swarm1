#!/usr/bin/env python3
"""Analyze benchmark data by AEAD algorithm."""
import csv
from collections import defaultdict

with open("benchmark_full_table_20260220.csv") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

# Group by AEAD and scenario
aead_stats = defaultdict(lambda: defaultdict(list))
for r in rows:
    aead = r["aead"]
    scenario = r["scenario"]
    if r["handshake_ms_drone"]:
        aead_stats[aead][scenario + "_hs_ms"].append(float(r["handshake_ms_drone"]))
    if r["throughput_mbps"]:
        aead_stats[aead][scenario + "_tp_mbps"].append(float(r["throughput_mbps"]))
    if r["rtt_avg_ms"]:
        aead_stats[aead][scenario + "_rtt_ms"].append(float(r["rtt_avg_ms"]))
    if r.get("fc_cpu_load_percent") and r["fc_cpu_load_percent"]:
        try:
            aead_stats[aead][scenario + "_cpu"].append(float(r["fc_cpu_load_percent"]))
        except:
            pass

print(f"Total rows: {len(rows)}")
scenarios = set(r["scenario"] for r in rows)
aeads = set(r["aead"] for r in rows)
print(f"Scenarios: {scenarios}")
print(f"AEADs: {aeads}")
print()

for aead in sorted(aead_stats.keys()):
    print(f"=== {aead} ===")
    data = aead_stats[aead]
    for key in sorted(data.keys()):
        vals = data[key]
        avg = sum(vals) / len(vals)
        mn = min(vals)
        mx = max(vals)
        print(f"  {key}: avg={avg:.2f} min={mn:.2f} max={mx:.2f} n={len(vals)}")
    print()

# Now look at individual AEAD power benchmarks
import os, json, glob

aead_power_dir = "individual_benchmarks/raw_data/5iter_test/raw/aead"
if os.path.isdir(aead_power_dir):
    print("=== INDIVIDUAL AEAD POWER BENCHMARKS ===")
    for f in sorted(glob.glob(os.path.join(aead_power_dir, "*.json"))):
        name = os.path.basename(f)
        with open(f) as fh:
            data = json.load(fh)
        # Extract power info
        power_mean = data.get("power_mean_w") or data.get("power_w_mean")
        energy = data.get("energy_j") or data.get("energy_total_j")
        duration = data.get("duration_s") or data.get("total_duration_s")
        ops = data.get("iterations") or data.get("ops_count")
        ops_per_s = data.get("ops_per_second")
        time_per_op = data.get("time_per_op_us") or data.get("avg_time_us")
        print(f"  {name}: power={power_mean}W energy={energy}J dur={duration}s ops={ops} ops/s={ops_per_s} us/op={time_per_op}")
else:
    print(f"Power dir not found: {aead_power_dir}")

# Also check per-suite detailed data for encrypt/decrypt nanos
print("\n=== AEAD ENCRYPT/DECRYPT TIMINGS FROM SUITE DATA ===")
suite_dir = "logs/benchmarks/runs/20260219/no-ddos"
if os.path.isdir(suite_dir):
    enc_times = defaultdict(list)
    dec_times = defaultdict(list)
    for f in sorted(os.listdir(suite_dir))[:100]:
        if not f.endswith(".json"):
            continue
        with open(os.path.join(suite_dir, f)) as fh:
            try:
                data = json.load(fh)
            except:
                continue
        aead = data.get("crypto_identity", {}).get("aead_algorithm", "")
        dp = data.get("data_plane", {})
        enc = dp.get("aead_encrypt_avg_ns")
        dec = dp.get("aead_decrypt_avg_ns")
        if aead and enc:
            enc_times[aead].append(enc)
        if aead and dec:
            dec_times[aead].append(dec)
    
    for aead in sorted(set(list(enc_times.keys()) + list(dec_times.keys()))):
        enc = enc_times.get(aead, [])
        dec = dec_times.get(aead, [])
        enc_avg = sum(enc) / len(enc) if enc else 0
        dec_avg = sum(dec) / len(dec) if dec else 0
        print(f"  {aead}: encrypt_avg={enc_avg:.0f}ns decrypt_avg={dec_avg:.0f}ns (n={len(enc)})")
