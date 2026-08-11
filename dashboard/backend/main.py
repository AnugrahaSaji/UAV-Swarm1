from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

# Handle imports depending on how run (module vs script)
try:
    from .models import RunSummary, ComprehensiveSuiteMetrics
    from .ingest import get_store
    from .routes.suites import router as suites_router
    from .routes.swarm_smt import router as swarm_smt_router
    from .settings_store import get_settings_store
except ImportError:
    from models import RunSummary, ComprehensiveSuiteMetrics
    from ingest import get_store
    from routes.suites import router as suites_router
    from routes.swarm_smt import router as swarm_smt_router
    from settings_store import get_settings_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

app = FastAPI(
    title="Secure-Tunnel Forensic Dashboard API",
    description="API for PQC forensic benchmark data — multi-run comparison & anomaly detection.",
    version="3.0"
)

# Register API routes
app.include_router(suites_router)
app.include_router(swarm_smt_router)

# CORS — use explicit origins for credentialed requests, wildcard for non-credentialed
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request schemas ──────────────────────────────────────────────────────────

class RunLabelRequest(BaseModel):
    run_id: str
    label: str
    run_type: str  # no_ddos | ddos_xgboost | ddos_txt

class ActiveRunsRequest(BaseModel):
    run_ids: List[str]

class ThresholdsRequest(BaseModel):
    thresholds: Dict[str, float]


# ── Root ─────────────────────────────────────────────────────────────────────

@app.get("/")
def read_root():
    return {"status": "online", "system": "Secure-Tunnel Forensic Dashboard v3"}


@app.get("/api/reload")
def reload_metrics():
    """Force reload of the metrics store from disk."""
    try:
        from .ingest import reload_store
    except ImportError:
        from ingest import reload_store
    store = reload_store()
    return {"status": "ok", "suite_count": store.suite_count, "run_count": store.run_count}



# ── Settings endpoints ───────────────────────────────────────────────────────

@app.get("/api/settings")
def get_settings():
    """Return all dashboard settings including run labels, active runs, thresholds."""
    ss = get_settings_store()
    store = get_store()
    settings = ss.get_all()
    # Attach ALL available runs — only 3-folder data is loaded now, no min_suites filter needed
    all_runs = store.list_runs()
    available_ids = {r.run_id for r in all_runs}
    run_dicts = []
    for r in all_runs:
        d = r.model_dump()
        d["run_type"] = store.get_run_type(r.run_id)
        run_dicts.append(d)
    settings["available_runs"] = run_dicts
    settings["scenario_status"] = store.get_scenario_status()

    # ── Auto-reconcile stale active_runs ─────────────────────────────────
    current_active = settings.get("active_runs", [])
    valid_active = [rid for rid in current_active if rid in available_ids]
    if len(valid_active) != len(current_active):
        # Stale IDs found — auto-select up to 3 newest runs if all stale
        if not valid_active:
            valid_active = sorted(available_ids, reverse=True)[:3]
        ss.set_active_runs(valid_active)
        settings["active_runs"] = valid_active

    # ── Auto-label unlabeled runs from ingested run_type ─────────────────
    run_labels = settings.get("run_labels", {})
    _TYPE_LABELS = {"no_ddos": "No DDoS (Baseline)", "ddos_xgboost": "DDoS – XGBoost", "ddos_txt": "DDoS – TXT"}
    for r in all_runs:
        if r.run_id not in run_labels:
            rt = store.get_run_type(r.run_id)
            auto_label = _TYPE_LABELS.get(rt, r.run_id)
            ss.set_run_label(r.run_id, auto_label, rt)
            run_labels[r.run_id] = {"label": auto_label, "type": rt}
    settings["run_labels"] = run_labels

    return settings

@app.post("/api/settings/run-label")
def set_run_label(req: RunLabelRequest):
    """Assign a label + type to a run_id."""
    ss = get_settings_store()
    ss.set_run_label(req.run_id, req.label, req.run_type)
    return {"ok": True}

@app.post("/api/settings/active-runs")
def set_active_runs(req: ActiveRunsRequest):
    """Set which runs are selected for display (up to 3)."""
    ss = get_settings_store()
    ss.set_active_runs(req.run_ids[:3])
    return {"ok": True, "active": req.run_ids[:3]}

@app.post("/api/settings/thresholds")
def set_thresholds(req: ThresholdsRequest):
    """Update anomaly detection thresholds."""
    ss = get_settings_store()
    ss.update_thresholds(req.thresholds)
    return {"ok": True}


# ── Multi-run comparison ─────────────────────────────────────────────────────

@app.get("/api/multi-run/compare")
def multi_run_compare(suite_id: str):
    """
    Compare the SAME suite across multiple runs (up to 3).
    Returns each run's full metrics for the given suite_id.
    """
    ss = get_settings_store()
    store = get_store()
    active = ss.get_active_runs()
    available_runs = [r.run_id for r in store.list_runs()]
    active = [rid for rid in active if rid in available_runs]
    if not active:
        # Fall back to all available runs
        active = available_runs

    results = []
    for run_id in active:
        key = f"{run_id}:{suite_id}"
        suite = store.get_suite_by_key(key)
        if suite is None:
            continue
        label_info = ss.get_run_label(run_id) or {"label": run_id, "type": store.get_run_type(run_id)}
        results.append({
            "run_id": run_id,
            "label": label_info.get("label", run_id),
            "run_type": store.get_run_type(run_id),
            "suite": suite.model_dump(),
        })
    if not results:
        raise HTTPException(status_code=404, detail=f"Suite '{suite_id}' not found in any active run")
    return {"suite_id": suite_id, "runs": results}


@app.get("/api/multi-run/overview")
def multi_run_overview():
    """
    Return aggregated KPI data for each active run — used by Overview page
    to show multi-run comparison cards.
    """
    ss = get_settings_store()
    store = get_store()
    active = ss.get_active_runs()
    available_runs = [r.run_id for r in store.list_runs()]
    active = [rid for rid in active if rid in available_runs]
    if not active:
        active = available_runs
    thresholds = ss.get_thresholds()

    overview = []
    for run_id in active:
        label_info = ss.get_run_label(run_id) or {"label": run_id, "type": store.get_run_type(run_id)}
        suites_for_run = [
            s for s in store._suites.values()
            if s.run_context.run_id == run_id
        ]
        if not suites_for_run:
            continue

        total = len(suites_for_run)
        passed = sum(1 for s in suites_for_run if s.validation.benchmark_pass_fail == "PASS")
        failed = sum(1 for s in suites_for_run if s.validation.benchmark_pass_fail == "FAIL")

        handshake_vals = [s.handshake.handshake_total_duration_ms for s in suites_for_run if s.handshake.handshake_total_duration_ms is not None]
        power_vals = [s.power_energy.power_avg_w for s in suites_for_run if s.power_energy.power_avg_w is not None]
        energy_vals = [s.power_energy.energy_total_j for s in suites_for_run if s.power_energy.energy_total_j is not None]
        loss_vals = [s.data_plane.packet_loss_ratio for s in suites_for_run if s.data_plane.packet_loss_ratio is not None]

        # Anomaly counts
        hs_threshold = thresholds.get("handshake_ms_high", 10000)
        loss_threshold = thresholds.get("packet_loss_warning", 0.01)
        anomaly_count = sum(1 for v in handshake_vals if v > hs_threshold) + sum(1 for v in loss_vals if v > loss_threshold)

        overview.append({
            "run_id": run_id,
            "label": label_info.get("label", run_id),
            "run_type": store.get_run_type(run_id),
            "total_suites": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
            "avg_handshake_ms": round(sum(handshake_vals) / len(handshake_vals), 2) if handshake_vals else None,
            "max_handshake_ms": round(max(handshake_vals), 2) if handshake_vals else None,
            "avg_power_w": round(sum(power_vals) / len(power_vals), 3) if power_vals else None,
            "avg_energy_j": round(sum(energy_vals) / len(energy_vals), 3) if energy_vals else None,
            "total_energy_j": round(sum(energy_vals), 3) if energy_vals else None,
            "avg_packet_loss": round(sum(loss_vals) / len(loss_vals), 6) if loss_vals else None,
            "anomaly_count": anomaly_count,
        })
    return {"runs": overview}


@app.get("/api/anomalies")
def detect_anomalies(run_id: Optional[str] = None):
    """
    Detect anomalies across suites based on configured thresholds.
    Returns list of flagged suites with reasons.
    """
    ss = get_settings_store()
    store = get_store()
    thresholds = ss.get_thresholds()

    target_suites = list(store._suites.values())
    if run_id:
        target_suites = [s for s in target_suites if s.run_context.run_id == run_id]

    anomalies = []
    for suite in target_suites:
        flags = []
        sid = suite.run_context.suite_id
        rid = suite.run_context.run_id

        # Handshake anomalies
        hs = suite.handshake.handshake_total_duration_ms
        if hs is not None:
            if hs > thresholds.get("handshake_ms_critical", 30000):
                flags.append({"metric": "handshake_ms", "value": hs, "severity": "critical", "threshold": thresholds.get("handshake_ms_critical", 30000)})
            elif hs > thresholds.get("handshake_ms_high", 10000):
                flags.append({"metric": "handshake_ms", "value": hs, "severity": "warning", "threshold": thresholds.get("handshake_ms_high", 10000)})

        # Packet loss
        loss = suite.data_plane.packet_loss_ratio
        if loss is not None:
            if loss > thresholds.get("packet_loss_critical", 0.05):
                flags.append({"metric": "packet_loss", "value": loss, "severity": "critical", "threshold": thresholds.get("packet_loss_critical", 0.05)})
            elif loss > thresholds.get("packet_loss_warning", 0.01):
                flags.append({"metric": "packet_loss", "value": loss, "severity": "warning", "threshold": thresholds.get("packet_loss_warning", 0.01)})

        # Handshake failure
        if suite.handshake.handshake_success is False:
            flags.append({"metric": "handshake_failure", "value": suite.handshake.handshake_failure_reason or "unknown", "severity": "critical", "threshold": None})

        # Benchmark fail
        if suite.validation.benchmark_pass_fail == "FAIL":
            flags.append({"metric": "benchmark_fail", "value": "FAIL", "severity": "critical", "threshold": None})

        # MAVLink integrity issues
        for field_name, attr in [
            ("crc_errors", "mavlink_packet_crc_error_count"),
            ("decode_errors", "mavlink_decode_error_count"),
            ("msg_drops", "mavlink_msg_drop_count"),
            ("out_of_order", "mavlink_out_of_order_count"),
            ("duplicates", "mavlink_duplicate_count"),
        ]:
            val = getattr(suite.mavlink_integrity, attr, None)
            if val is not None and val > 0:
                flags.append({"metric": f"mavlink_{field_name}", "value": val, "severity": "warning", "threshold": 0})

        # Replay / auth drops
        if suite.data_plane.drop_replay and suite.data_plane.drop_replay > 0:
            flags.append({"metric": "replay_drops", "value": suite.data_plane.drop_replay, "severity": "critical", "threshold": 0})
        if suite.data_plane.drop_auth and suite.data_plane.drop_auth > 0:
            flags.append({"metric": "auth_drops", "value": suite.data_plane.drop_auth, "severity": "critical", "threshold": 0})

        if flags:
            anomalies.append({
                "suite_id": sid,
                "run_id": rid,
                "key": f"{rid}:{sid}",
                "kem": suite.crypto_identity.kem_algorithm,
                "sig": suite.crypto_identity.sig_algorithm,
                "flags": flags,
                "severity": "critical" if any(f["severity"] == "critical" for f in flags) else "warning",
            })

    anomalies.sort(key=lambda a: (0 if a["severity"] == "critical" else 1, a["suite_id"]))
    return {"anomalies": anomalies, "total": len(anomalies), "thresholds": thresholds}


@app.get("/api/multi-run/all-suites-compare")
def multi_run_all_suites_compare():
    """
    Compare ALL suites across all active runs.
    Returns per-suite metrics for each run type, plus overhead calculations.
    This powers the CrossRunAnalysis "understand everything" page.
    """
    ss = get_settings_store()
    store = get_store()
    active = ss.get_active_runs()
    labels = ss.get_all().get("run_labels", {})
    available_runs = [r.run_id for r in store.list_runs()]
    active = [rid for rid in active if rid in available_runs]
    if not active:
        active = available_runs

    # Build per-suite data
    suite_map: Dict[str, dict] = {}

    run_info_list = []
    for run_id in active:
        run_type = store.get_run_type(run_id)
        label_info = labels.get(run_id, {})
        rt = label_info.get("type", run_type)
        run_label = label_info.get("label", run_id)
        run_info_list.append({"run_id": run_id, "label": run_label, "run_type": rt})

        for key, suite in store._suites.items():
            if not key.startswith(run_id + ":"):
                continue
            sid = suite.run_context.suite_id
            if sid not in suite_map:
                suite_map[sid] = {
                    "suite_id": sid,
                    "kem": suite.crypto_identity.kem_algorithm,
                    "sig": suite.crypto_identity.sig_algorithm,
                    "aead": suite.crypto_identity.aead_algorithm,
                    "nist": suite.crypto_identity.suite_security_level,
                    "kem_family": suite.crypto_identity.kem_family,
                    "sig_family": suite.crypto_identity.sig_family,
                    "runs": {},
                }
            hs = suite.handshake
            cp = suite.crypto_primitives
            sd = suite.system_drone
            pe = suite.power_energy
            dp = suite.data_plane
            lj = suite.latency_jitter
            mi = suite.mavlink_integrity
            fc = suite.fc_telemetry
            suite_map[sid]["runs"][rt] = {
                "handshake_ms": hs.handshake_total_duration_ms,
                "protocol_hs_ms": hs.protocol_handshake_duration_ms,
                "e2e_hs_ms": hs.end_to_end_handshake_duration_ms,
                "handshake_success": hs.handshake_success,
                "kem_keygen_ms": cp.kem_keygen_time_ms,
                "kem_encaps_ms": cp.kem_encapsulation_time_ms,
                "kem_decaps_ms": cp.kem_decapsulation_time_ms,
                "sig_sign_ms": cp.signature_sign_time_ms,
                "sig_verify_ms": cp.signature_verify_time_ms,
                "total_crypto_ms": cp.total_crypto_time_ms,
                "cpu_avg_pct": sd.cpu_usage_avg_percent,
                "cpu_peak_pct": sd.cpu_usage_peak_percent,
                "memory_mb": sd.memory_rss_mb,
                "temperature_c": sd.temperature_c,
                "load_avg_1m": sd.load_avg_1m,
                "power_avg_w": pe.power_avg_w,
                "power_peak_w": pe.power_peak_w,
                "energy_j": pe.energy_total_j,
                "energy_per_hs_j": pe.energy_per_handshake_j,
                "voltage_v": pe.voltage_avg_v,
                "current_a": pe.current_avg_a,
                "goodput_mbps": dp.goodput_mbps,
                "packet_loss": dp.packet_loss_ratio,
                "packets_sent": dp.packets_sent,
                "packets_dropped": dp.packets_dropped,
                "drop_replay": dp.drop_replay,
                "drop_auth": dp.drop_auth,
                "rtt_avg_ms": lj.rtt_avg_ms,
                "rtt_p95_ms": lj.rtt_p95_ms,
                "jitter_avg_ms": lj.jitter_avg_ms,
                "owl_avg_ms": lj.one_way_latency_avg_ms,
                "mavlink_crc_errors": mi.mavlink_packet_crc_error_count,
                "mavlink_decode_errors": mi.mavlink_decode_error_count,
                "mavlink_ooo": mi.mavlink_out_of_order_count,
                "mavlink_duplicates": mi.mavlink_duplicate_count,
                "benchmark_pass": suite.validation.benchmark_pass_fail,
                "fc_battery_v": fc.fc_battery_voltage_v,
                "fc_battery_pct": fc.fc_battery_remaining_percent,
            }

    suites_list = sorted(suite_map.values(), key=lambda x: x["suite_id"])

    # Compute overhead summary (ddos vs baseline)
    def _avg(vals):
        valid = [v for v in vals if v is not None]
        return sum(valid) / len(valid) if valid else None

    def _overhead_pct(baseline, target):
        if baseline is None or target is None or baseline == 0:
            return None
        return round((target - baseline) / baseline * 100, 1)

    overhead = {}
    for rt in ["ddos_xgboost", "ddos_txt"]:
        baseline_vals = {}
        target_vals = {}
        for s in suites_list:
            base = s["runs"].get("no_ddos", {})
            tgt = s["runs"].get(rt, {})
            for metric in ["cpu_avg_pct", "cpu_peak_pct", "temperature_c", "memory_mb",
                           "power_avg_w", "energy_j", "handshake_ms", "goodput_mbps",
                           "rtt_avg_ms", "jitter_avg_ms", "packet_loss"]:
                if metric not in baseline_vals:
                    baseline_vals[metric] = []
                    target_vals[metric] = []
                bv = base.get(metric)
                tv = tgt.get(metric)
                if bv is not None and tv is not None:
                    baseline_vals[metric].append(bv)
                    target_vals[metric].append(tv)
        oh = {}
        for metric in baseline_vals:
            b = _avg(baseline_vals[metric])
            t = _avg(target_vals[metric])
            oh[metric] = {
                "baseline_avg": round(b, 4) if b is not None else None,
                "target_avg": round(t, 4) if t is not None else None,
                "delta_pct": _overhead_pct(b, t),
                "delta_abs": round(t - b, 4) if b is not None and t is not None else None,
            }
        overhead[rt] = oh

    return {"suites": suites_list, "runs": run_info_list, "overhead": overhead}


@app.get("/api/latency-summary")
def latency_summary(run_id: Optional[str] = None):
    """
    Return per-suite latency & transport metrics for the LatencyAnalysis page.
    Includes handshake timing, RTT, jitter, one-way latency, and goodput.
    """
    store = get_store()
    items = []
    for key, suite in store._suites.items():
        if run_id and suite.run_context.run_id != run_id:
            continue
        lj = suite.latency_jitter
        dp = suite.data_plane
        hs = suite.handshake
        ci = suite.crypto_identity
        pe = suite.power_energy
        items.append({
            "suite_id": suite.run_context.suite_id,
            "run_id": suite.run_context.run_id,
            "key": key,
            "kem_algorithm": ci.kem_algorithm,
            "sig_algorithm": ci.sig_algorithm,
            "aead_algorithm": ci.aead_algorithm,
            "suite_security_level": ci.suite_security_level,
            "kem_family": ci.kem_family,
            # Handshake
            "handshake_total_duration_ms": hs.handshake_total_duration_ms,
            "handshake_success": hs.handshake_success,
            "protocol_handshake_duration_ms": hs.protocol_handshake_duration_ms,
            "end_to_end_handshake_duration_ms": hs.end_to_end_handshake_duration_ms,
            # Latency & Jitter
            "rtt_avg_ms": lj.rtt_avg_ms,
            "rtt_p95_ms": lj.rtt_p95_ms,
            "rtt_sample_count": lj.rtt_sample_count,
            "rtt_valid": lj.rtt_valid,
            "one_way_latency_avg_ms": lj.one_way_latency_avg_ms,
            "one_way_latency_p95_ms": lj.one_way_latency_p95_ms,
            "one_way_latency_valid": lj.one_way_latency_valid,
            "jitter_avg_ms": lj.jitter_avg_ms,
            "jitter_p95_ms": lj.jitter_p95_ms,
            "latency_sample_count": lj.latency_sample_count,
            # Transport
            "goodput_mbps": dp.goodput_mbps,
            "achieved_throughput_mbps": dp.achieved_throughput_mbps,
            "packets_sent": dp.packets_sent,
            "packets_received": dp.packets_received,
            "packets_dropped": dp.packets_dropped,
            "packet_loss_ratio": dp.packet_loss_ratio,
            "packet_delivery_ratio": dp.packet_delivery_ratio,
            # Power
            "power_avg_w": pe.power_avg_w,
            "energy_total_j": pe.energy_total_j,
            # Validation
            "benchmark_pass_fail": suite.validation.benchmark_pass_fail,
        })
    return {"suites": items, "count": len(items)}
