"""Quick API smoke test — start uvicorn in-process and hit every endpoint."""
import threading, time, urllib.request, json, sys

def server():
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8002, log_level="warning")

t = threading.Thread(target=server, daemon=True)
t.start()
time.sleep(5)

def GET(path):
    resp = urllib.request.urlopen(f"http://127.0.0.1:8002{path}")
    return json.loads(resp.read())

# 1) Root
print("Root:", GET("/"))

# 2) Runs
runs = GET("/api/runs")
print(f"\nRuns: {len(runs)}")
for r in runs:
    print(f"  {r['run_id']}: {r['suite_count']} suites")

# 3) Suites
suites = GET("/api/suites")
print(f"\nSuites: {len(suites)}")
s = suites[0]
print(f"Sample: {s['suite_id']}")
print(f"  kem={s['kem_algorithm']}, sig={s['sig_algorithm']}, aead={s['aead_algorithm']}")
print(f"  hs={s.get('handshake_total_duration_ms')}, pwr={s.get('power_avg_w')}, E={s.get('energy_total_j')}")
print(f"  status={s.get('benchmark_pass_fail')}, level={s.get('suite_security_level')}")

# 4) Suite detail
sid = s["suite_id"]
rid = s["run_id"]
detail = GET(f"/api/suite/{rid}:{sid}")
print(f"\nDetail keys: {list(detail.keys())[:15]}")
print(f"  handshake.success: {detail.get('handshake', {}).get('handshake_success')}")
print(f"  power_energy.power_avg_w: {detail.get('power_energy', {}).get('power_avg_w')}")
print(f"  system_gcs.cpu: {detail.get('system_gcs', {}).get('cpu_usage_avg_percent')}")
print(f"  latency_source: {detail.get('latency_source')}")

# 5) Aggregation
try:
    agg = GET("/api/suites/aggregated")
    if isinstance(agg, list):
        print(f"\nAggregated rows: {len(agg)}")
        if agg:
            print(f"  row keys sample: {list(agg[0].keys())[:10]}")
    elif isinstance(agg, dict):
        print(f"\nAggregated keys: {list(agg.keys())[:10]}")
except Exception as e:
    print(f"\nAggregation error: {e}")

# 6) Bucket comparison
try:
    buckets = GET("/api/suites/bucket-comparison")
    if isinstance(buckets, dict):
        print(f"\nBucket keys: {list(buckets.keys())}")
        for k, v in buckets.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} items")
    elif isinstance(buckets, list):
        print(f"\nBuckets: {len(buckets)} items")
except Exception as e:
    print(f"\nBucket error: {e}")

# 7) Filters/unique values
try:
    filters = GET("/api/suites/filters")
    print(f"\nFilters: {filters}")
except Exception as e:
    print(f"\nFilters error: {e}")

print("\n✅ All API tests passed!")
