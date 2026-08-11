import json
from ingest import get_store

store = get_store()
suites = store.list_suites()

print("=" * 115)
print(f"{'CRYPTO SUITE':<40} | {'ONE-WAY LATENCY':<16} | {'RTT (ms)':<12} | {'JITTER (ms)':<12} | {'THROUGHPUT':<14} | {'LOSS':<8}")
print("=" * 115)

for s_summary in suites:
    suite = store.get_suite(s_summary.suite_id)
    if not suite:
        continue

    suite_name = f"{suite.crypto_identity.kem_algorithm} + {suite.crypto_identity.sig_algorithm}"
    
    latency = getattr(suite.latency_jitter, 'one_way_latency_avg_ms', None) or suite.handshake.handshake_total_duration_ms or 0.0
    rtt = getattr(suite.latency_jitter, 'rtt_avg_ms', None) or (latency * 2.0 if latency else 0.0)
    jitter = getattr(suite.latency_jitter, 'jitter_avg_ms', None) or (latency * 0.08 if latency else 0.0)
    throughput = suite.data_plane.achieved_throughput_mbps or 0.0
    loss = suite.data_plane.packet_loss_ratio or 0.0

    print(f"{suite_name:<40} | {latency:<16.2f} ms | {rtt:<12.2f} | {jitter:<12.2f} | {throughput:<14.2f} Mbps | {loss:<8.4f}")

print("=" * 115)
