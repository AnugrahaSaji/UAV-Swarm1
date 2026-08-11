import json
import statistics
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"c:/Users/burak/ptojects/secure-tunnel")
OUT = ROOT / "vtc" / "results_analysis_generated.tex"

IDLE_MW = 3309.0

LATEST = ROOT / "bench_ddos_results" / "20260302_135859"
BASELINE = json.loads((LATEST / "baseline.json").read_text(encoding="utf-8"))
XGB = json.loads((LATEST / "xgb.json").read_text(encoding="utf-8"))
TST = json.loads((LATEST / "tst.json").read_text(encoding="utf-8"))
CMP = json.loads((LATEST / "comparison.json").read_text(encoding="utf-8"))

RAW = ROOT / "v2-1.8ghz" / "raw_data" / "raw"
KEM_DIR = RAW / "kem"
SIG_DIR = RAW / "sig"
AEAD_DIR = RAW / "aead"


def esc(s: str) -> str:
    return s.replace("_", "\\_").replace("+", "{+}")


def mean(vals):
    return sum(vals) / len(vals) if vals else 0.0


def pctl(vals, q):
    if not vals:
        return 0.0
    vals = sorted(vals)
    k = (len(vals) - 1) * q / 100.0
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    if f == c:
        return vals[f]
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def nist_from_name(name: str) -> str:
    n = name.lower()
    if "ml-kem-512" in n or "hqc-128" in n or "348864" in n or "-44" in n or "falcon-512" in n or "128s" in n:
        return "L1"
    if "ml-kem-768" in n or "hqc-192" in n or "460896" in n or "-65" in n or "192s" in n:
        return "L3"
    return "L5"


def kem_alias(name: str) -> str:
    m = {
        "ML-KEM-512": "K-ML512",
        "ML-KEM-768": "K-ML768",
        "ML-KEM-1024": "K-ML1024",
        "HQC-128": "K-HQC128",
        "HQC-192": "K-HQC192",
        "HQC-256": "K-HQC256",
        "Classic-McEliece-348864": "K-MCE348",
        "Classic-McEliece-460896": "K-MCE460",
        "Classic-McEliece-8192128": "K-MCE819",
    }
    return m.get(name, name)


def sig_alias(name: str) -> str:
    m = {
        "ML-DSA-44": "S-DSA44",
        "ML-DSA-65": "S-DSA65",
        "ML-DSA-87": "S-DSA87",
        "Falcon-512": "S-F512",
        "Falcon-1024": "S-F1024",
        "SPHINCS+-SHA2-128s-simple": "S-SP128s",
        "SPHINCS+-SHA2-192s-simple": "S-SP192s",
        "SPHINCS+-SHA2-256s-simple": "S-SP256s",
    }
    return m.get(name, name)


def aead_alias(name: str) -> str:
    m = {
        "AES-256-GCM": "A-AG",
        "ChaCha20-Poly1305": "A-CP",
        "Ascon-128a": "A-AS",
    }
    return m.get(name, name)


def parse_suite(sid: str):
    p = sid.replace("cs-", "").split("-")
    # classicmceliece348864-aesgcm-falcon512
    kem = p[0]
    aead = p[1]
    sig = "-".join(p[2:])
    return kem, aead, sig


# --- KEM primitive table from raw 1.8GHz ---
kem_ops = defaultdict(dict)
for fp in KEM_DIR.glob("*.json"):
    d = json.loads(fp.read_text(encoding="utf-8"))
    alg = d["algorithm"]
    op = d["operation"]
    t_ms = [x / 1_000_000 for x in d["timing"]["perf_ns"]]
    p_w = d["power"]["power_mean_w"]
    e_uj = [x * 1e6 for x in d["power"]["energy_j"]]
    kem_ops[alg][op] = {
        "med_ms": statistics.median(t_ms),
        "p95_ms": pctl(t_ms, 95),
        "power_mw": mean(p_w) * 1000,
        "delta_mw": mean(p_w) * 1000 - IDLE_MW,
        "energy_uj": mean(e_uj),
        "pk": d["sizes"].get("public_key"),
        "ct": d["sizes"].get("ciphertext"),
    }

# --- SIG primitive table from raw 1.8GHz ---
sig_ops = defaultdict(dict)
for fp in SIG_DIR.glob("*.json"):
    d = json.loads(fp.read_text(encoding="utf-8"))
    alg = d["algorithm"]
    op = d["operation"]
    t_ms = [x / 1_000_000 for x in d["timing"]["perf_ns"]]
    p_w = d["power"]["power_mean_w"]
    e_uj = [x * 1e6 for x in d["power"]["energy_j"]]
    sig_ops[alg][op] = {
        "med_ms": statistics.median(t_ms),
        "p95_ms": pctl(t_ms, 95),
        "power_mw": mean(p_w) * 1000,
        "delta_mw": mean(p_w) * 1000 - IDLE_MW,
        "energy_uj": mean(e_uj),
        "sig": d["sizes"].get("signature"),
        "pk": d["sizes"].get("public_key"),
    }

# --- AEAD detail from raw 1.8GHz ---
aead_rows = []
for fp in AEAD_DIR.glob("*.json"):
    d = json.loads(fp.read_text(encoding="utf-8"))
    algo = d["algorithm"]
    op = d["operation"]
    payload = d["payload_size"]
    ct = d["sizes"].get("ciphertext")
    t_ns = d["timing"]["perf_ns"]
    t_us = [x / 1000 for x in t_ns]
    p_w = d["power"]["power_mean_w"]
    e_uj = [x * 1e6 for x in d["power"]["energy_j"]]

    tp = []
    for n in t_ns:
        sec = n / 1e9
        if sec > 0:
            tp.append((payload / sec) / 1e6)

    aead_rows.append({
        "algo": algo,
        "op": op,
        "payload": payload,
        "ct": ct,
        "mean_us": mean(t_us),
        "p95_us": pctl(t_us, 95),
        "power_mw": mean(p_w) * 1000,
        "delta_mw": mean(p_w) * 1000 - IDLE_MW,
        "energy_uj": mean(e_uj),
        "tp_mbs": mean(tp),
    })

aead_rows.sort(key=lambda r: (r["algo"], r["payload"], r["op"]))

# --- Suite pair summary from latest run ---
pair = defaultdict(lambda: defaultdict(list))
for r in BASELINE["results"]:
    k = (r["kem"], r["sig"], r["nist_level"])
    pair[k]["hs_ms"].append(r["mean_us"] / 1000)
    pair[k]["hs_p95_ms"].append(r["p95_us"] / 1000)
    pair[k]["energy_mj"].append(r["avg_energy_mj_per_hs"])
    pair[k]["power_mw"].append(r["avg_power_mw"])
    pair[k]["cpu_pct"].append(r["cpu_avg"])
    pair[k]["pk"].append(r["public_key_bytes"])
    pair[k]["sig"].append(r["signature_bytes"])
    pair[k]["ct"].append(r["ciphertext_bytes"])

pair_rows = []
for (kem, sig, level), d in pair.items():
    pair_rows.append({
        "kem": kem,
        "sig": sig,
        "level": level,
        "hs_ms": mean(d["hs_ms"]),
        "hs_p95_ms": mean(d["hs_p95_ms"]),
        "energy_mj": mean(d["energy_mj"]),
        "power_mw": mean(d["power_mw"]),
        "delta_mw": mean(d["power_mw"]) - IDLE_MW,
        "cpu": mean(d["cpu_pct"]),
        "wire": int(round(mean(d["pk"]) + mean(d["sig"]) + mean(d["ct"]) + 32)),
    })
pair_rows.sort(key=lambda r: (r["level"], r["hs_ms"]))

# --- Handshake phase decomposition (representative suites) ---
ranked = sorted(BASELINE["results"], key=lambda x: x["mean_us"])
reps = [
    ranked[0],
    next(x for x in ranked if x["nist_level"] == "L3"),
    next(x for x in ranked if x["nist_level"] == "L5"),
    max(BASELINE["results"], key=lambda x: x["mean_us"]),
]

# --- DDoS interaction summary from comparison ---
per = CMP["per_suite"]
bl_p = mean([x["baseline_power_mw"] for x in per])
xg_p = mean([x["xgb_power_mw"] for x in per])
ts_p = mean([x["tst_power_mw"] for x in per])
bl_c = mean([x["baseline_cpu_avg"] for x in per])
xg_c = mean([x["xgb_cpu_avg"] for x in per])
ts_c = mean([x["tst_cpu_avg"] for x in per])
bl_h = mean([x["baseline_mean_ms"] for x in per])
xg_h = mean([x["xgb_mean_ms"] for x in per])
ts_h = mean([x["tst_mean_ms"] for x in per])

# --- graceful degradation boundary picks ---
def level_of_sid(sid):
    s = sid.lower()
    if any(x in s for x in ["mlkem512", "hqc128", "348864"]):
        return "L1"
    if any(x in s for x in ["mlkem768", "hqc192", "460896"]):
        return "L3"
    return "L5"

def kem_family(kem_name: str) -> str:
    if "ML-KEM" in kem_name:
        return "ML-KEM"
    if "HQC" in kem_name:
        return "HQC"
    return "Classic-McEliece"


def agg_pair(results):
    out = defaultdict(lambda: defaultdict(list))
    for r in results:
        k = (r["kem"], r["sig"])
        out[k]["hs_ms"].append(r["mean_us"] / 1000.0)
        out[k]["energy_mj"].append(r["avg_energy_mj_per_hs"])
        out[k]["power_mw"].append(r["avg_power_mw"])
        out[k]["cpu"].append(r["cpu_avg"])
        out[k]["pk"].append(r["public_key_bytes"])
        out[k]["sig_bytes"].append(r["signature_bytes"])
        out[k]["ct"].append(r["ciphertext_bytes"])
    agg = {}
    for k, d in out.items():
        agg[k] = {
            "hs_ms": mean(d["hs_ms"]),
            "energy_mj": mean(d["energy_mj"]),
            "power_mw": mean(d["power_mw"]),
            "cpu": mean(d["cpu"]),
            "wire": int(round(mean(d["pk"]) + mean(d["sig_bytes"]) + mean(d["ct"]) + 32)),
        }
    return agg


agg_no = agg_pair(BASELINE["results"])
agg_xg = agg_pair(XGB["results"])
agg_ts = agg_pair(TST["results"])

kem_order = [
    "ML-KEM-512", "ML-KEM-768", "ML-KEM-1024",
    "HQC-128", "HQC-192", "HQC-256",
    "Classic-McEliece-348864", "Classic-McEliece-460896", "Classic-McEliece-8192128",
]

sig_subset_6 = [
    "ML-DSA-44", "Falcon-512",
    "ML-DSA-65", "SPHINCS+-SHA2-192s-simple",
    "ML-DSA-87", "Falcon-1024",
]

ddos_by_level = defaultdict(lambda: defaultdict(list))
for x in per:
    lv = level_of_sid(x["suite_id"])
    ddos_by_level[lv]["no"].append(x["baseline_mean_ms"])
    ddos_by_level[lv]["xg"].append(x["xgb_mean_ms"])
    ddos_by_level[lv]["ts"].append(x["tst_mean_ms"])
    ddos_by_level[lv]["dxg"].append(x["xgb_mean_ms"] - x["baseline_mean_ms"])
    ddos_by_level[lv]["dts"].append(x["tst_mean_ms"] - x["baseline_mean_ms"])

pqc_on_ddos = defaultdict(lambda: defaultdict(list))
for x in per:
    sid = x["suite_id"].lower()
    fam = "ML-KEM" if "mlkem" in sid else ("HQC" if "hqc" in sid else "Classic-McEliece")
    pqc_on_ddos[fam]["xg_dp"].append(x["xgb_power_mw"] - x["baseline_power_mw"])
    pqc_on_ddos[fam]["ts_dp"].append(x["tst_power_mw"] - x["baseline_power_mw"])
    pqc_on_ddos[fam]["xg_dc"].append(x["xgb_cpu_avg"] - x["baseline_cpu_avg"])
    pqc_on_ddos[fam]["ts_dc"].append(x["tst_cpu_avg"] - x["baseline_cpu_avg"])

lines = []
lines.append("% Auto-generated from raw benchmark artifacts; do not edit manually.")
lines.append("% Source: bench_ddos_results/20260302_135859 + v2-1.8ghz/raw_data/raw")
lines.append("% Generated by vtc/build_results_analysis_tables.py")
lines.append("")
lines.append("\\subsection{Alias Definitions (Used in All Tables)}")
lines.append("\\begin{table}[t]")
lines.append("\\centering")
lines.append("\\caption{Meaningful aliases used in the results tables.}")
lines.append("\\footnotesize")
lines.append("\\setlength{\\tabcolsep}{2.5pt}")
lines.append("\\begin{tabular}{@{}lll@{}}\\toprule")
lines.append("Alias & Type & Primitive \\\\ \\midrule")
for k in kem_order:
    lines.append(f"{kem_alias(k)} & KEM & {esc(k)} \\\\")
for s in ["ML-DSA-44","ML-DSA-65","ML-DSA-87","Falcon-512","Falcon-1024","SPHINCS+-SHA2-128s-simple","SPHINCS+-SHA2-192s-simple","SPHINCS+-SHA2-256s-simple"]:
    lines.append(f"{sig_alias(s)} & SIG & {esc(s)} \\\\")
for a in ["AES-256-GCM","ChaCha20-Poly1305","Ascon-128a"]:
    lines.append(f"{aead_alias(a)} & AEAD & {esc(a)} \\\\")
lines.append("\\bottomrule\\end{tabular}")
lines.append("\\label{tab:alias-def}")
lines.append("\\end{table}")
lines.append("")

# KEM table
lines.append("\\subsection{KEM Primitives (1.8GHz Aggressive Benchmark)}")
lines.append("\\begin{table*}[t]")
lines.append("\\centering")
lines.append("\\caption{KEM primitive metrics from raw 1.8GHz run (200 iterations). $\\Delta P = P_{mean}-P_{idle}$ with $P_{idle}=3309$ mW.}")
lines.append("\\footnotesize")
lines.append("\\setlength{\\tabcolsep}{3pt}")
lines.append("\\begin{tabular}{@{}llrrrrrrr@{}}\\toprule")
lines.append("Alias & NIST & KeyGen ms & Encap ms & Decap ms & KeyGen $\\Delta P$ mW & Encap $\\Delta P$ mW & Decap $\\Delta P$ mW & (PK,CT) bytes \\\\ \\midrule")
for k in sorted(kem_ops.keys(), key=lambda x: (nist_from_name(x), x)):
    d = kem_ops[k]
    kg, ec, dc = d.get("keygen"), d.get("encapsulate"), d.get("decapsulate")
    if not (kg and ec and dc):
        continue
    lines.append(
        f"{kem_alias(k)} & {nist_from_name(k)} & {kg['med_ms']:.3f} & {ec['med_ms']:.3f} & {dc['med_ms']:.3f} & {kg['delta_mw']:.1f} & {ec['delta_mw']:.1f} & {dc['delta_mw']:.1f} & ({kg['pk']},{ec['ct']}) \\\\" 
    )
lines.append("\\bottomrule\\end{tabular}")
lines.append("\\label{tab:kem-primitives-raw}")
lines.append("\\end{table*}")
lines.append("")

# SIG table
lines.append("\\subsection{Digital Signature Primitives (1.8GHz Aggressive Benchmark)}")
lines.append("\\begin{table*}[t]")
lines.append("\\centering")
lines.append("\\caption{Signature primitive metrics from raw 1.8GHz run (200 iterations). $\\Delta P = P_{mean}-P_{idle}$ with $P_{idle}=3309$ mW.}")
lines.append("\\footnotesize")
lines.append("\\setlength{\\tabcolsep}{3pt}")
lines.append("\\begin{tabular}{@{}llrrrrrrr@{}}\\toprule")
lines.append("Alias & NIST & KeyGen ms & Sign ms & Verify ms & KeyGen $\\Delta P$ mW & Sign $\\Delta P$ mW & Verify $\\Delta P$ mW & Sig bytes \\\\ \\midrule")
for s in sorted(sig_ops.keys(), key=lambda x: (nist_from_name(x), x)):
    d = sig_ops[s]
    kg, sg, vf = d.get("keygen"), d.get("sign"), d.get("verify")
    if not (kg and sg and vf):
        continue
    sig_bytes = sg.get("sig") if sg.get("sig") is not None else "--"
    lines.append(
        f"{sig_alias(s)} & {nist_from_name(s)} & {kg['med_ms']:.3f} & {sg['med_ms']:.3f} & {vf['med_ms']:.3f} & {kg['delta_mw']:.1f} & {sg['delta_mw']:.1f} & {vf['delta_mw']:.1f} & {sig_bytes} \\\\" 
    )
lines.append("\\bottomrule\\end{tabular}")
lines.append("\\label{tab:sig-primitives-raw}")
lines.append("\\end{table*}")
lines.append("")

# AEAD table
lines.append("\\subsection{AEAD Metrics (Power Baseline-Subtracted)}")
lines.append("\\begin{table*}[t]")
lines.append("\\centering")
lines.append("\\caption{AEAD metrics from raw 1.8GHz benchmark. $\\Delta P = P_{mean}-3309$ mW. Interval-normalized power energy reported per operation and projected over $t=10$ s at measured throughput.}")
lines.append("\\footnotesize")
lines.append("\\setlength{\\tabcolsep}{2.6pt}")
lines.append("\\begin{tabular}{@{}llrrrrrrrr@{}}\\toprule")
lines.append("Alias & Op & Payload B & Mean $\\mu$s & P95 $\\mu$s & Throughput MB/s & Mean $\\Delta P$ mW & Energy $\\mu$J/op & Ciphertext B & Overhead B \\\\ \\midrule")
for r in aead_rows:
    ct_disp = r["ct"] if r["ct"] is not None else "--"
    ov = (r["ct"] - r["payload"]) if (r["ct"] is not None and r["payload"] is not None) else "--"
    lines.append(
        f"{aead_alias(r['algo'])} & {r['op']} & {r['payload']} & {r['mean_us']:.2f} & {r['p95_us']:.2f} & {r['tp_mbs']:.2f} & {r['delta_mw']:.1f} & {r['energy_uj']:.2f} & {ct_disp} & {ov} \\\\" 
    )
lines.append("\\bottomrule\\end{tabular}")
lines.append("\\label{tab:aead-all-cols-raw}")
lines.append("\\end{table*}")
lines.append("")

# Suite combinatorics + formula
lines.append("\\subsection{Unified Suite Table (9\\,$\\times$\\,6, AEAD-Averaged, Three DDoS Modes)}")
lines.append("Handshake metric in the table is computed as $T_{hs}=T_{build\\_hello}+T_{parse\\_verify}+T_{encap}+T_{decap}+T_{derive\\_client}+T_{derive\\_server}$. Values are averaged over the three AEAD variants so AEAD impact is isolated in Table~\\ref{tab:aead-all-cols-raw}.")
lines.append("\\begin{table*}[t]")
lines.append("\\centering")
lines.append("\\caption{9\\,$\\times$\\,6 KEM-SIG suite table with no-ddos, ddos-xgboost, and ddos-tst columns (latest run).}")
lines.append("\\footnotesize")
lines.append("\\setlength{\\tabcolsep}{2.1pt}")
lines.append("\\begin{tabular}{@{}llrrrrrrr@{}}\\toprule")
lines.append("KEM alias & SIG alias & NIST & No-DDoS ms & XGB ms & TST ms & XGB\\,$\\Delta$\\% & TST\\,$\\Delta$\\% & Wire B \\\\ \\midrule")
for kem in kem_order:
    for sig in sig_subset_6:
        key = (kem, sig)
        lv = nist_from_name(kem)
        no = agg_no.get(key)
        xg = agg_xg.get(key)
        ts = agg_ts.get(key)
        if no:
            no_hs = f"{no['hs_ms']:.2f}"
            xg_hs = f"{xg['hs_ms']:.2f}" if xg else "--"
            ts_hs = f"{ts['hs_ms']:.2f}" if ts else "--"
            dxg = f"{((xg['hs_ms']-no['hs_ms'])/no['hs_ms']*100):+.1f}" if xg and no['hs_ms'] > 0 else "--"
            dts = f"{((ts['hs_ms']-no['hs_ms'])/no['hs_ms']*100):+.1f}" if ts and no['hs_ms'] > 0 else "--"
            wire = str(no["wire"])
        else:
            no_hs, xg_hs, ts_hs, dxg, dts, wire = "--", "--", "--", "--", "--", "--"
        lines.append(f"{kem_alias(kem)} & {sig_alias(sig)} & {lv} & {no_hs} & {xg_hs} & {ts_hs} & {dxg} & {dts} & {wire} \\\\")
lines.append("\\bottomrule\\end{tabular}")
lines.append("\\label{tab:suite-9x6-unified}")
lines.append("\\end{table*}")
lines.append("")

# DDoS interaction tables
lines.append("\\subsection{DDoS Impact on PQC}")
lines.append("\\begin{table}[t]")
lines.append("\\centering")
lines.append("\\caption{DDoS impact on PQC handshake latency by NIST level (AEAD+suite averaged, latest run).}")
lines.append("\\footnotesize")
lines.append("\\begin{tabular}{@{}lrrrrr@{}}\\toprule")
lines.append("Level & No-DDoS ms & XGB ms & TST ms & XGB\\,$\\Delta$ ms & TST\\,$\\Delta$ ms \\\\ \\midrule")
for lv in ["L1", "L3", "L5"]:
    d = ddos_by_level[lv]
    lines.append(f"{lv} & {mean(d['no']):.2f} & {mean(d['xg']):.2f} & {mean(d['ts']):.2f} & {mean(d['dxg']):+.2f} & {mean(d['dts']):+.2f} \\\\")
lines.append("\\bottomrule\\end{tabular}")
lines.append("\\label{tab:ddos-impact-on-pqc}")
lines.append("\\end{table}")

lines.append("\\subsection{PQC Impact on DDoS}")
lines.append("\\begin{table}[t]")
lines.append("\\centering")
lines.append("\\caption{PQC family impact on DDoS detector overhead (latest run, per-suite averaged).}")
lines.append("\\footnotesize")
lines.append("\\begin{tabular}{@{}lrrrr@{}}\\toprule")
lines.append("KEM family & XGB\\,$\\Delta$ P mW & TST\\,$\\Delta$ P mW & XGB\\,$\\Delta$ CPU\\% & TST\\,$\\Delta$ CPU\\% \\\\ \\midrule")
for fam in ["ML-KEM", "HQC", "Classic-McEliece"]:
    d = pqc_on_ddos[fam]
    lines.append(f"{fam} & {mean(d['xg_dp']):.1f} & {mean(d['ts_dp']):.1f} & {mean(d['xg_dc']):.1f} & {mean(d['ts_dc']):.1f} \\\\")
lines.append("\\bottomrule\\end{tabular}")
lines.append("\\label{tab:pqc-impact-on-ddos}")
lines.append("\\end{table}")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {OUT}")
