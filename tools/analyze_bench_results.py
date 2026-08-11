#!/usr/bin/env python3
"""Quick analysis of benchmark results with power data."""
import json, statistics

DIR = "bench_ddos_results/20260302_135859"

with open(f"{DIR}/comparison.json") as f:
    data = json.load(f)
s = data["summary"]

print("=== BENCHMARK SUMMARY (with INA219 power) ===")
print(f"Total suites: {s['total_suites']}")
print(f"XGB overhead:   mean={s['xgb_overhead_mean_pct']}%  median={s['xgb_overhead_median_pct']}%  max={s['xgb_overhead_max_pct']}%")
print(f"TST overhead:   mean={s['tst_overhead_mean_pct']}%  median={s['tst_overhead_median_pct']}%  max={s['tst_overhead_max_pct']}%")
print(f"CPU ordering:   {s['cpu_ordering_correct']} correct / {s['cpu_ordering_violated']} violated")
print(f"Power ordering: {s['power_ordering_correct']} correct / {s['power_ordering_violated']} violated")
print()

for phase_name, phase_file in [("BASELINE", "baseline.json"), ("XGB", "xgb.json"), ("TST", "tst.json")]:
    with open(f"{DIR}/{phase_file}") as f:
        pd = json.load(f)
    pvs = [r.get("avg_power_mw") for r in pd["results"] if r.get("avg_power_mw")]
    vvs = [r.get("avg_voltage_v") for r in pd["results"] if r.get("avg_voltage_v")]
    cvs = [r.get("avg_current_ma") for r in pd["results"] if r.get("avg_current_ma")]
    if pvs:
        print(f"{phase_name} power:   min={min(pvs):.0f}  avg={sum(pvs)/len(pvs):.0f}  max={max(pvs):.0f} mW  ({len(pvs)}/{len(pd['results'])} suites)")
    else:
        print(f"{phase_name} power:   NO DATA")
    if vvs:
        print(f"{phase_name} voltage: min={min(vvs):.2f}  avg={sum(vvs)/len(vvs):.2f}  max={max(vvs):.2f} V")
    if cvs:
        print(f"{phase_name} current: min={min(cvs):.0f}  avg={sum(cvs)/len(cvs):.0f}  max={max(cvs):.0f} mA")
    print()
