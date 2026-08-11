#!/usr/bin/env python3
"""Generate IEEE-formatted LaTeX tables from canonical CSV datasets.

Usage:
    python skills/latex-tables/scripts/generate_tables.py
"""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATASETS = ROOT / "paper" / "vtc_fall" / "datasets"
TABLES = ROOT / "paper" / "vtc_fall" / "tables"
TABLES.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        print(f"  SKIP: {path.name} not found")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fmt(val, decimals=1):
    """Format a numeric string to fixed decimal places."""
    try:
        return f"{float(val):.{decimals}f}"
    except (ValueError, TypeError):
        return str(val) if val else "---"


def generate_aead_table():
    """Generate AEAD comparison table (tab:aead)."""
    rows = read_csv(DATASETS / "aead_latency.csv")
    if not rows:
        return

    # Filter to 280-byte payload (MAVLink typical), encrypt+decrypt
    target_payload = "280"
    ciphers = {}
    for row in rows:
        if str(row.get("payload_bytes")) == target_payload:
            cipher = row["cipher"]
            op = row["operation"]
            if cipher not in ciphers:
                ciphers[cipher] = {}
            ciphers[cipher][op] = row

    if not ciphers:
        # Fallback: use whatever payload sizes exist
        for row in rows:
            cipher = row["cipher"]
            op = row["operation"]
            key = f"{cipher}_{row.get('payload_bytes', '')}"
            if key not in ciphers:
                ciphers[key] = {}
            ciphers[key][op] = row

    tex = r"""\begin{table}[t]
\centering
\caption{AEAD Cipher Comparison on Raspberry Pi~4 (\num{10000} iterations, native C)}
\label{tab:aead}
\footnotesize
\begin{tabular}{l S[table-format=3.2] S[table-format=3.2] S[table-format=3.2] S[table-format=2.2]}
\toprule
{Cipher} & {Encrypt (\si{\micro\second})} & {Decrypt (\si{\micro\second})} & {Pipeline (\si{\micro\second})} & {Throughput (\si{\mega\byte\per\second})} \\
\midrule
"""

    for cipher, ops in sorted(ciphers.items()):
        enc = ops.get("encrypt", {})
        dec = ops.get("decrypt", {})
        enc_us = fmt(enc.get("mean_us", ""))
        dec_us = fmt(dec.get("mean_us", ""))
        try:
            pipeline = fmt(float(enc.get("mean_us", 0)) + float(dec.get("mean_us", 0)))
        except (ValueError, TypeError):
            pipeline = "---"
        tput = fmt(enc.get("throughput_mbps", ""), 2)
        name = cipher.split("_")[0] if "_" in cipher else cipher
        tex += f"{name:<22} & {enc_us} & {dec_us} & {pipeline} & {tput} \\\\\n"

    tex += r"""\bottomrule
\end{tabular}
\end{table}
"""

    out = TABLES / "tab_aead.tex"
    out.write_text(tex, encoding="utf-8")
    print(f"  tab_aead.tex generated")


def generate_handshake_table():
    """Generate handshake overhead table (tab:hs_overhead)."""
    rows = read_csv(DATASETS / "handshake_overhead.csv")
    if not rows:
        return

    # Group by NIST level (extract from suite name)
    tex = r"""\begin{table}[t]
\centering
\caption{PQC Handshake Overhead by Suite (Top~10 by Drone Latency)}
\label{tab:hs_overhead}
\footnotesize
\begin{tabular}{l l S[table-format=4.1] S[table-format=4.1] S[table-format=1.2] S[table-format=1.2]}
\toprule
{Suite} & {AEAD} & {HS Drone (\si{\milli\second})} & {HS GCS (\si{\milli\second})} & {RTT avg (\si{\milli\second})} & {Loss} \\
\midrule
"""

    # Sort by drone handshake time, take top 10
    valid = [r for r in rows if r.get("handshake_ms_drone")]
    valid.sort(key=lambda r: float(r.get("handshake_ms_drone", 0) or 0))
    for row in valid[:10]:
        suite = row["suite"]
        # Truncate long suite names
        short = suite.replace("cs-", "").replace("-", " ")[:30]
        tex += (f"{short:<32} & {row.get('aead', ''):<16} "
                f"& {fmt(row.get('handshake_ms_drone', ''))} "
                f"& {fmt(row.get('handshake_ms_gcs', ''))} "
                f"& {fmt(row.get('rtt_avg_ms', ''))} "
                f"& {fmt(row.get('packet_loss_ratio', ''), 3)} \\\\\n")

    tex += r"""\bottomrule
\end{tabular}
\end{table}
"""

    out = TABLES / "tab_hs_overhead.tex"
    out.write_text(tex, encoding="utf-8")
    print(f"  tab_hs_overhead.tex generated")


def main():
    print("=== LaTeX Table Generation ===")
    print(f"Input: {DATASETS}")
    print(f"Output: {TABLES}")
    print()
    generate_aead_table()
    generate_handshake_table()
    print("\nDone.")


if __name__ == "__main__":
    main()
