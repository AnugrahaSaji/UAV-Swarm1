#!/usr/bin/env python3
"""Generate LaTeX table rows from bench_v3 JSON data."""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "bench_results_v3", "20260310_103448")

# ── helpers ──────────────────────────────────────────────────────────────────
def load(name):
    with open(os.path.join(DATA_DIR, name)) as f:
        return json.load(f)

def fmt_ms(v):
    """Format ms value for LaTeX: thousands separator."""
    if v < 0.01:
        return f"{v:.3f}"
    if v < 10:
        return f"{v:.2f}"
    if v < 100:
        return f"{v:.1f}"
    if v < 1000:
        return f"{v:.1f}"
    iv = int(round(v))
    s = f"{iv:,}".replace(",", "\\,")
    return s

def fmt_uj(v):
    """Format µJ as mJ string."""
    mj = v / 1000.0
    if mj < 0.1:
        return f"{mj:.3f}"
    if mj < 10:
        return f"{mj:.1f}"
    if mj < 1000:
        return f"{int(round(mj)):,}".replace(",", "\\,")
    return f"{int(round(mj)):,}".replace(",", "\\,")

def pct(old, new):
    if old == 0:
        return "---"
    d = (new - old) / old * 100
    sign = "+" if d >= 0 else ""
    return f"${sign}{d:.1f}$"

# ── Alias maps ───────────────────────────────────────────────────────────────
KEM_ALIAS = {
    "ML-KEM-512": "MK512", "ML-KEM-768": "MK768", "ML-KEM-1024": "MK1024",
    "HQC-128": "HQ128", "HQC-192": "HQ192", "HQC-256": "HQ256",
    "Classic-McEliece-348864": "MC348",
    "Classic-McEliece-460896": "MC460",
    "Classic-McEliece-8192128": "MC8192",
}
SIG_ALIAS = {
    "Falcon-512": "FA512", "Falcon-1024": "FA1024",
    "ML-DSA-44": "MD44", "ML-DSA-65": "MD65", "ML-DSA-87": "MD87",
    "SPHINCS+-SHA2-128s-simple": "SP128",
    "SPHINCS+-SHA2-192s-simple": "SP192",
    "SPHINCS+-SHA2-256s-simple": "SP256",
}

LEVEL_MAP = {"L1": 1, "L3": 3, "L5": 5}

# BW values from algorithm parameters (constant, not measured)
BW_MAP = {
    ("MK512","FA512"): "2\\,227", ("MK512","MD44"): "3\\,988",
    ("MK512","SP128"): "9\\,424",
    ("HQ128","FA512"): "7\\,335", ("HQ128","MD44"): "9\\,102",
    ("HQ128","SP128"): "14\\,538",
    ("MC348","FA512"): "261\\,870", ("MC348","MD44"): "263\\,636",
    ("MC348","SP128"): "269\\,072",
    ("MK768","MD65"): "5\\,581", ("MK768","SP192"): "18\\,496",
    ("HQ192","MD65"): "16\\,809", ("HQ192","SP192"): "29\\,724",
    ("MC460","MD65"): "527\\,625", ("MC460","SP192"): "---",
    ("MK1024","FA1024"): "4\\,410", ("MK1024","MD87"): "7\\,763",
    ("MK1024","SP256"): "32\\,928",
    ("HQ256","FA1024"): "22\\,943", ("HQ256","MD87"): "26\\,293",
    ("HQ256","SP256"): "51\\,458",
    ("MC8192","FA1024"): "1\\,359\\,303", ("MC8192","MD87"): "1\\,362\\,659",
    ("MC8192","SP256"): "1\\,387\\,824",
}

# ── Load data ────────────────────────────────────────────────────────────────
hs_base = {r["suite_id"]: r for r in load("handshake_baseline.json")["results"]}
hs_xgb  = {r["suite_id"]: r for r in load("handshake_xgboost.json")["results"]}
hs_tst  = {r["suite_id"]: r for r in load("handshake_tst.json")["results"]}

aead_base = load("aead_baseline.json")["results"]
aead_xgb  = load("aead_xgboost.json")["results"]
aead_tst  = load("aead_tst.json")["results"]

# ── TABLE: tab:suite_full ────────────────────────────────────────────────────
print("=" * 80)
print("TABLE: tab:suite_full  (Baseline handshake, 24 suites)")
print("=" * 80)

# Group by level
by_level = {}
for sid, r in hs_base.items():
    ka = KEM_ALIAS.get(r["kem"], r["kem"])
    sa = SIG_ALIAS.get(r["sig"], r["sig"])
    lvl = LEVEL_MAP[r["nist_level"]]
    by_level.setdefault(lvl, []).append((r["mean_ms"], ka, sa, r))

for lvl in [1, 3, 5]:
    suites = sorted(by_level[lvl], key=lambda x: x[0])
    fastest = suites[0][0]
    n = len(suites)
    label = f"Level {lvl}"
    print(f"\\midrule")
    print(f"\\multirow{{{n}}}{{*}}{{\\rotatebox[origin=c]{{90}}{{\\textbf{{{label}}}}}}}")
    for t_hs, ka, sa, r in suites:
        bw = BW_MAP.get((ka, sa), "---")
        e_mj = fmt_uj(r["per_hs_energy_uj"])
        rho = t_hs / fastest
        if rho < 10:
            rho_s = f"{rho:.1f}$\\times$"
        else:
            rho_s = f"{int(round(rho)):,}$\\times$".replace(",", "\\,")
        print(f"& {ka:<7s} & {sa:<6s} & {fmt_ms(t_hs):<8s} & {bw:<14s} & {e_mj:<8s} & {rho_s} \\\\")

# ── TABLE: tab:full_aesgcm ──────────────────────────────────────────────────
print()
print("=" * 80)
print("TABLE: tab:full_aesgcm  (24 suites × 3 detectors)")
print("=" * 80)

# Color map for log-bar macro
def bar_family(kem_alias):
    if kem_alias.startswith("MK"):
        return "lattice"
    if kem_alias.startswith("HQ") or kem_alias.startswith("MC"):
        return "codebased"
    return "hashbased"

def sig_family(sig_alias):
    if sig_alias.startswith("SP"):
        return "hashbased"
    return None

def suite_family(ka, sa):
    # If SIG is SPHINCS, use hashbased; else use KEM family
    if sa.startswith("SP"):
        return "hashbased"
    return bar_family(ka)

# Sort order for the table: group by level, then by families
level_order = {1: 0, 3: 1, 5: 2}
kem_order = {"MC348": 0, "MC460": 0, "MC8192": 0, "HQ128": 1, "HQ192": 1, "HQ256": 1, "MK512": 2, "MK768": 2, "MK1024": 2}

all_suites = []
for sid in hs_base:
    rb = hs_base[sid]
    rx = hs_xgb.get(sid)
    rt = hs_tst.get(sid)
    if not rx or not rt:
        continue
    ka = KEM_ALIAS.get(rb["kem"], rb["kem"])
    sa = SIG_ALIAS.get(rb["sig"], rb["sig"])
    lvl = LEVEL_MAP[rb["nist_level"]]
    all_suites.append((lvl, ka, sa, rb, rx, rt))

# Sort by level, then KEM family, then SIG
sig_sort = {"FA512": 0, "FA1024": 0, "MD44": 1, "MD65": 1, "MD87": 1, "SP128": 2, "SP192": 2, "SP256": 2}
all_suites.sort(key=lambda x: (level_order[x[0]], kem_order.get(x[1], 9), sig_sort.get(x[2], 9)))

prev_lvl = None
for lvl, ka, sa, rb, rx, rt in all_suites:
    if lvl != prev_lvl:
        if prev_lvl is not None:
            print("\\midrule")
        print(f"% L{lvl} suites")
        prev_lvl = lvl

    b_ms = rb["mean_ms"]
    x_ms = rx["mean_ms"]
    t_ms = rt["mean_ms"]

    d_x = pct(b_ms, x_ms)
    d_t = pct(b_ms, t_ms)

    fam = suite_family(ka, sa)

    # Format bar values (integer ms for display)
    def bar_val(v):
        return f"{v:.1f}" if v < 100 else f"{int(round(v))}"

    b_bar = f"\\bvlog{{{b_ms:.1f}}}{{5}}{{{fam}}}{{{bar_val(b_ms)}}}"
    x_bar = f"\\bvlog{{{x_ms:.1f}}}{{5}}{{{fam}}}{{{bar_val(x_ms)}}}"
    t_bar = f"\\bvlog{{{t_ms:.1f}}}{{5}}{{{fam}}}{{{bar_val(t_ms)}}}"

    # For very large values (>10000), use \bvlogL
    if b_ms > 10000:
        b_bar = f"\\bvlogL{{{b_ms/1000:.3f}}}{{5}}{{{fam}}}{{{int(round(b_ms))}}}"
    if x_ms > 10000:
        x_bar = f"\\bvlogL{{{x_ms/1000:.3f}}}{{5}}{{{fam}}}{{{int(round(x_ms))}}}"
    if t_ms > 10000:
        t_bar = f"\\bvlogL{{{t_ms/1000:.3f}}}{{5}}{{{fam}}}{{{int(round(t_ms))}}}"

    suite_name = f"{ka}+{sa}"
    print(f"{suite_name:<18s} & {b_bar} & {x_bar} & {t_bar} "
          f"& {d_x} & {d_t} "
          f"& {rb['cpu_avg']:.1f} & {rx['cpu_avg']:.1f} & {rt['cpu_avg']:.1f} "
          f"& {rb['temp_c']:.1f} & {rx['temp_c']:.1f} & {rt['temp_c']:.1f} \\\\")

# ── TABLE: tab:aead ──────────────────────────────────────────────────────────
print()
print("=" * 80)
print("TABLE: tab:aead  (AEAD performance, baseline)")
print("=" * 80)

# Build dict: aead_name -> {enc: ..., dec: ...}
aead_dict = {}
for r in aead_base:
    name = r["aead_name"]
    op = r["operation"]
    aead_dict.setdefault(name, {})[op] = r

AEAD_ALIAS = {
    "AES-128-GCM": ("A1", "128"), "AES-128-CCM": ("C1", "128"),
    "Ascon-128a": ("AS", "128"),
    "AES-192-GCM": ("A9", "192"), "AES-192-CCM": ("C9", "192"),
    "TinyJambu-192": ("TJ", "192"),
    "AES-256-GCM": ("AG", "256"), "AES-256-CCM": ("C6", "256"),
    "ChaCha20-Poly1305": ("CC", "256"),
}

AEAD_ORDER = ["AES-128-GCM", "AES-128-CCM", "Ascon-128a",
              "AES-192-GCM", "AES-192-CCM",
              "AES-256-GCM", "AES-256-CCM", "ChaCha20-Poly1305"]

prev_tier = None
for name in AEAD_ORDER:
    alias, tier = AEAD_ALIAS[name]
    ops = aead_dict.get(name, {})
    enc = ops.get("encrypt", {})
    dec = ops.get("decrypt", {})

    if not enc or enc.get("error"):
        continue

    enc_us = enc["mean_us"]
    dec_us = dec["mean_us"]
    enc_uj = enc["per_op_energy_uj"]
    dec_uj = dec["per_op_energy_uj"]
    e_256b = enc_uj + dec_uj
    e_bit = e_256b / 2048 * 1000  # nJ/bit

    tag_b = 16

    if tier != prev_tier:
        if prev_tier is not None:
            print("\\midrule")
        prev_tier = tier

    short_name = name
    print(f"  & {alias} & {short_name:<20s} & {enc_us:.2f}  & {dec_us:.2f}   & {tag_b}  & {e_256b:.1f}  & {e_bit:.1f} \\\\")

# ── TABLE: tab:default_matrix ────────────────────────────────────────────────
print()
print("=" * 80)
print("TABLE: tab:default_matrix  (3 primary AEADs × 3 detectors)")
print("=" * 80)

# Use AES-256-GCM, ChaCha20-Poly1305, Ascon-128a
PRIMARY_AEADS = ["AES-256-GCM", "ChaCha20-Poly1305", "Ascon-128a"]
PRIMARY_LABELS = {"AES-256-GCM": "AES-GCM", "ChaCha20-Poly1305": "ChaCha20", "Ascon-128a": "Ascon-128a"}
DET_LABELS = {"Baseline": "Base", "XGBoost": "XGB", "TST": "TST"}

def build_aead_lookup(results):
    d = {}
    for r in results:
        d.setdefault(r["aead_name"], {})[r["operation"]] = r
    return d

aead_b = build_aead_lookup(aead_base)
aead_x = build_aead_lookup(aead_xgb)
aead_t = build_aead_lookup(aead_tst)

for aead_name in PRIMARY_AEADS:
    label = PRIMARY_LABELS[aead_name]
    for det_name, det_label, dataset in [("Baseline", "Base", aead_b),
                                          ("XGBoost", "XGB", aead_x),
                                          ("TST", "TST", aead_t)]:
        ops = dataset.get(aead_name, {})
        enc = ops.get("encrypt", {})
        dec = ops.get("decrypt", {})
        if not enc:
            continue
        enc_ns = int(round(enc["mean_us"] * 1000))
        dec_ns = int(round(dec["mean_us"] * 1000))
        cpu = (enc["cpu_avg"] + dec["cpu_avg"]) / 2
        temp = (enc["temp_c"] + dec["temp_c"]) / 2
        if det_label == "Base":
            print(f"\\multirow{{3}}{{*}}{{\\tiny {label}}}")
        print(f" & {det_label} & {enc_ns} & {dec_ns} & {cpu:.1f} & {temp:.1f} \\\\")
    print("\\midrule")

print()
print("=" * 80)
print("AEAD SCHEDULER SEEDS (for tab:sched offline benchmarks)")
print("=" * 80)
for name in AEAD_ORDER:
    ops = aead_dict.get(name, {})
    enc = ops.get("encrypt", {})
    dec = ops.get("decrypt", {})
    if enc and not enc.get("error"):
        print(f"  {name}: enc={enc['mean_us']:.2f}µs, dec={dec['mean_us']:.2f}µs")
