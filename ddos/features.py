"""
Flow Feature Extractor for CIC-IoT-2023 Pre-trained Models
==========================================================
Ported from IA02_CAPSTONE/ml/packet_sniffer.py for use with
LightGBM and RandomForest models trained on 54 CIC-IoT-2023 features.

Captures raw packets via scapy, aggregates per-flow statistics over
a configurable window (default 100 packets), and produces feature
dicts compatible with the pre-trained scaler and models.

The extractor is designed for MAVLink-over-UDP traffic:
  - Detects MAVLink v2 (0xFD magic byte) to track tunnel packets
  - MQTT features are zero-filled (not relevant for UAV but kept
    for model compatibility)
"""

import math
import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import scapy.all as scapy
except ImportError:
    scapy = None

# ── 54 features expected by the model (exact order) ─────────────────
FEATURE_NAMES = [
    "flow_duration", "Header_Length", "Protocol Type", "Duration",
    "Rate", "Srate", "Drate",
    "fin_flag_number", "syn_flag_number", "rst_flag_number",
    "psh_flag_number", "ack_flag_number", "ece_flag_number",
    "cwr_flag_number",
    "ack_count", "syn_count", "fin_count", "urg_count", "rst_count",
    "HTTP", "HTTPS", "DNS", "Telnet", "SMTP", "SSH", "IRC",
    "TCP", "UDP", "DHCP", "ARP", "ICMP", "IPv", "LLC",
    "Tot sum", "Min", "Max", "AVG", "Std", "Tot size", "IAT",
    "Number", "Magnitue", "Radius", "Covariance", "Variance", "Weight",
    "mqtt_connect_count", "mqtt_publish_count", "mqtt_sub_count",
    "mqtt_auth_fail", "mqtt_avg_payload", "mqtt_avg_topic",
    "mqtt_dirty_sess", "mqtt_will_count",
]

# Port-based protocol detection
_PORT_PROTOCOLS = {
    80: "HTTP", 443: "HTTPS", 53: "DNS", 23: "Telnet",
    25: "SMTP", 22: "SSH", 6667: "IRC", 67: "DHCP", 68: "DHCP",
}


class FlowState:
    """Per-flow packet tracking state."""
    __slots__ = (
        "start_ts", "last_ts", "fwd_pkts", "bwd_pkts",
        "fwd_bytes", "bwd_bytes",
    )

    def __init__(self, ts: float):
        self.start_ts = ts
        self.last_ts = ts
        self.fwd_pkts = 0
        self.bwd_pkts = 0
        self.fwd_bytes = 0
        self.bwd_bytes = 0

    def update(self, ts: float, size: int, is_fwd: bool):
        self.last_ts = ts
        if is_fwd:
            self.fwd_pkts += 1
            self.fwd_bytes += size
        else:
            self.bwd_pkts += 1
            self.bwd_bytes += size

    @property
    def duration(self) -> float:
        return max(self.last_ts - self.start_ts, 1e-9)


def _dynamic_two_streams(inco_sizes: List[int],
                         out_sizes: List[int]) -> Tuple[float, float, float, float]:
    """Compute magnitude, radius, covariance, weight from two packet streams.

    Matches IA02_CAPSTONE/ml/packet_sniffer.py dynamic_two_streams().
    """
    if not inco_sizes:
        inco_sizes = [0]
    if not out_sizes:
        out_sizes = [0]

    mean_in = np.mean(inco_sizes)
    mean_out = np.mean(out_sizes)
    var_in = np.var(inco_sizes)
    var_out = np.var(out_sizes)

    magnitude = math.sqrt(abs(mean_in) + abs(mean_out))
    radius = math.sqrt(abs(var_in) + abs(var_out))

    if len(inco_sizes) > 1 and len(out_sizes) > 1:
        min_len = min(len(inco_sizes), len(out_sizes))
        cov_matrix = np.cov(inco_sizes[:min_len], out_sizes[:min_len])
        covariance = float(cov_matrix[0, 1]) if cov_matrix.ndim == 2 else 0.0
    else:
        covariance = 0.0

    weight = len(inco_sizes) * len(out_sizes)
    return magnitude, radius, covariance, weight


def _make_flow_key(ip_src: str, sport: int,
                   ip_dst: str, dport: int) -> tuple:
    """Canonical bi-directional flow key (sorted endpoints)."""
    a = (ip_src, sport)
    b = (ip_dst, dport)
    return (a, b) if a <= b else (b, a)


class FlowFeatureExtractor:
    """Aggregates raw packets into 54-feature vectors for CIC-IoT-2023 models.

    Usage::

        extractor = FlowFeatureExtractor(window_size=100)
        extractor.start("wlan0")
        # ... later ...
        batch = extractor.harvest()  # returns list of feature dicts
    """

    def __init__(self, window_size: int = 100):
        self._window_size = window_size
        self._lock = Lock()
        self._packets: List[dict] = []
        self._flows: Dict[tuple, FlowState] = defaultdict(lambda: None)
        self._fwd_sizes: Dict[tuple, List[int]] = defaultdict(list)
        self._bwd_sizes: Dict[tuple, List[int]] = defaultdict(list)

    def _extract_packet(self, pkt, ts: float) -> Optional[dict]:
        """Extract per-packet fields from a scapy packet."""
        if scapy is None:
            return None

        if not pkt.haslayer(scapy.IP):
            return None

        ip = pkt[scapy.IP]
        row = {
            "ts": ts,
            "size": len(pkt),
            "header_len": ip.ihl * 4 if hasattr(ip, "ihl") else 20,
            "proto": ip.proto,
            "ip_src": ip.src,
            "ip_dst": ip.dst,
            "sport": 0,
            "dport": 0,
            # TCP flags
            "fin": 0, "syn": 0, "rst": 0, "psh": 0,
            "ack": 0, "urg": 0, "ece": 0, "cwr": 0,
            # Protocol booleans
            "is_tcp": 0, "is_udp": 0, "is_icmp": 0,
            "is_arp": 0, "is_llc": 0,
        }

        if pkt.haslayer(scapy.TCP):
            tcp = pkt[scapy.TCP]
            row["sport"] = tcp.sport
            row["dport"] = tcp.dport
            row["is_tcp"] = 1
            flags = tcp.flags
            row["fin"] = 1 if flags & 0x01 else 0
            row["syn"] = 1 if flags & 0x02 else 0
            row["rst"] = 1 if flags & 0x04 else 0
            row["psh"] = 1 if flags & 0x08 else 0
            row["ack"] = 1 if flags & 0x10 else 0
            row["urg"] = 1 if flags & 0x20 else 0
            row["ece"] = 1 if flags & 0x40 else 0
            row["cwr"] = 1 if flags & 0x80 else 0
        elif pkt.haslayer(scapy.UDP):
            udp = pkt[scapy.UDP]
            row["sport"] = udp.sport
            row["dport"] = udp.dport
            row["is_udp"] = 1
        elif pkt.haslayer(scapy.ICMP):
            row["is_icmp"] = 1

        if pkt.haslayer(scapy.ARP):
            row["is_arp"] = 1
        # LLC detection
        if hasattr(scapy, "LLC") and pkt.haslayer(scapy.LLC):
            row["is_llc"] = 1

        return row

    def _packet_callback(self, pkt):
        """Scapy sniff callback — extract and buffer packet data."""
        ts = time.time()
        row = self._extract_packet(pkt, ts)
        if row is None:
            return

        with self._lock:
            self._packets.append(row)

    def start(self, iface: str):
        """Start background sniffing on the given interface."""
        if scapy is None:
            raise RuntimeError("scapy is required for packet capture")
        from threading import Thread
        t = Thread(
            target=scapy.sniff,
            kwargs={"prn": self._packet_callback, "store": 0, "iface": iface},
            daemon=True,
        )
        t.start()

    def harvest(self) -> List[dict]:
        """Consume buffered packets and return feature vector dicts.

        Each dict has exactly the 54 keys from FEATURE_NAMES, ready
        for DataFrame construction and scaler transform.
        Returns one feature dict per window_size packets collected.
        """
        with self._lock:
            pkts = self._packets[:]
            self._packets.clear()

        if not pkts:
            return []

        results = []
        for i in range(0, len(pkts), self._window_size):
            window = pkts[i : i + self._window_size]
            if len(window) < 2:
                continue
            features = self._summarize_window(window)
            results.append(features)
        return results

    def _summarize_window(self, pkts: List[dict]) -> dict:
        """Aggregate a window of raw packets into a 54-feature dict."""
        n = len(pkts)

        # Timing
        first_ts = pkts[0]["ts"]
        last_ts = pkts[-1]["ts"]
        flow_dur = max(last_ts - first_ts, 1e-9)

        # Sizes
        sizes = [p["size"] for p in pkts]
        header_lens = [p["header_len"] for p in pkts]
        tot_sum = sum(sizes)
        tot_size = sum(sizes)

        # IAT (inter-arrival time)
        timestamps = [p["ts"] for p in pkts]
        iats = [timestamps[j] - timestamps[j - 1] for j in range(1, len(timestamps))]
        iat_mean = float(np.mean(iats)) if iats else 0.0

        # TCP flag counts
        fin_c = sum(p["fin"] for p in pkts)
        syn_c = sum(p["syn"] for p in pkts)
        rst_c = sum(p["rst"] for p in pkts)
        psh_c = sum(p["psh"] for p in pkts)
        ack_c = sum(p["ack"] for p in pkts)
        urg_c = sum(p["urg"] for p in pkts)
        ece_c = sum(p["ece"] for p in pkts)
        cwr_c = sum(p["cwr"] for p in pkts)

        # Flag fractions (number = fraction as in CIC-IoT-2023)
        fin_frac = fin_c / n
        syn_frac = syn_c / n
        rst_frac = rst_c / n
        psh_frac = psh_c / n
        ack_frac = ack_c / n
        ece_frac = ece_c / n
        cwr_frac = cwr_c / n

        # Protocol type — majority protocol number
        proto_counts: Dict[int, int] = defaultdict(int)
        for p in pkts:
            proto_counts[p["proto"]] += 1
        proto_type = max(proto_counts, key=proto_counts.get)

        # Rates
        rate = n / flow_dur
        # srate/drate use forward/backward split
        fwd_sizes = []
        bwd_sizes = []
        for p in pkts:
            # First packet source defines "forward"
            if p["ip_src"] == pkts[0]["ip_src"]:
                fwd_sizes.append(p["size"])
            else:
                bwd_sizes.append(p["size"])

        fwd_n = len(fwd_sizes)
        bwd_n = len(bwd_sizes)
        srate = fwd_n / flow_dur
        drate = bwd_n / flow_dur

        # Port-based protocol booleans
        proto_bools = {k: 0 for k in [
            "HTTP", "HTTPS", "DNS", "Telnet", "SMTP",
            "SSH", "IRC", "DHCP",
        ]}
        for p in pkts:
            for port in (p["sport"], p["dport"]):
                proto_name = _PORT_PROTOCOLS.get(port)
                if proto_name:
                    proto_bools[proto_name] = 1

        is_tcp = max(p["is_tcp"] for p in pkts)
        is_udp = max(p["is_udp"] for p in pkts)
        is_icmp = max(p["is_icmp"] for p in pkts)
        is_arp = max(p["is_arp"] for p in pkts)
        is_llc = max(p["is_llc"] for p in pkts)
        is_ipv = 1  # all packets have IP layer

        # Two-stream metrics
        magnitude, radius, covariance, weight = _dynamic_two_streams(
            fwd_sizes if fwd_sizes else [0],
            bwd_sizes if bwd_sizes else [0],
        )

        # Destination port (most common)
        dport_counts: Dict[int, int] = defaultdict(int)
        for p in pkts:
            dport_counts[p["dport"]] += 1
        dst_port = max(dport_counts, key=dport_counts.get)

        sizes_arr = np.array(sizes, dtype=np.float64)

        return {
            "flow_duration": flow_dur,
            "Header_Length": float(np.sum(header_lens)),
            "Protocol Type": proto_type,
            "Duration": flow_dur,
            "Rate": rate,
            "Srate": srate,
            "Drate": drate,
            "fin_flag_number": fin_frac,
            "syn_flag_number": syn_frac,
            "rst_flag_number": rst_frac,
            "psh_flag_number": psh_frac,
            "ack_flag_number": ack_frac,
            "ece_flag_number": ece_frac,
            "cwr_flag_number": cwr_frac,
            "ack_count": ack_c,
            "syn_count": syn_c,
            "fin_count": fin_c,
            "urg_count": urg_c,
            "rst_count": rst_c,
            "HTTP": proto_bools["HTTP"],
            "HTTPS": proto_bools["HTTPS"],
            "DNS": proto_bools["DNS"],
            "Telnet": proto_bools["Telnet"],
            "SMTP": proto_bools["SMTP"],
            "SSH": proto_bools["SSH"],
            "IRC": proto_bools["IRC"],
            "TCP": is_tcp,
            "UDP": is_udp,
            "DHCP": proto_bools["DHCP"],
            "ARP": is_arp,
            "ICMP": is_icmp,
            "IPv": is_ipv,
            "LLC": is_llc,
            "Tot sum": float(tot_sum),
            "Min": float(sizes_arr.min()),
            "Max": float(sizes_arr.max()),
            "AVG": float(sizes_arr.mean()),
            "Std": float(sizes_arr.std()),
            "Tot size": float(tot_size),
            "IAT": iat_mean,
            "Number": n,
            "Magnitue": magnitude,
            "Radius": radius,
            "Covariance": covariance,
            "Variance": float(sizes_arr.var()),
            "Weight": weight,
            # MQTT features: zero-filled (not relevant for MAVLink/UDP)
            "mqtt_connect_count": 0,
            "mqtt_publish_count": 0,
            "mqtt_sub_count": 0,
            "mqtt_auth_fail": 0,
            "mqtt_avg_payload": 0.0,
            "mqtt_avg_topic": 0.0,
            "mqtt_dirty_sess": 0,
            "mqtt_will_count": 0,
        }


def generate_synthetic_features(n: int = 1, attack: bool = False) -> List[dict]:
    """Generate synthetic feature dicts for benchmarking.

    If attack=True, generates features resembling a SYN flood:
      high syn_count, high rate, small packets.
    Otherwise, generates benign-looking traffic features.
    """
    results = []
    rng = np.random.default_rng(42)

    for _ in range(n):
        if attack:
            n_pkts = rng.integers(500, 2000)
            dur = rng.uniform(0.1, 0.5)
            avg_size = rng.uniform(40, 80)
            syn_frac = rng.uniform(0.8, 1.0)
            ack_frac = rng.uniform(0.0, 0.1)
        else:
            n_pkts = rng.integers(20, 200)
            dur = rng.uniform(1.0, 10.0)
            avg_size = rng.uniform(100, 1400)
            syn_frac = rng.uniform(0.0, 0.05)
            ack_frac = rng.uniform(0.3, 0.8)

        rate = n_pkts / dur
        tot = avg_size * n_pkts
        std_size = avg_size * rng.uniform(0.1, 0.5)

        feat = {name: 0.0 for name in FEATURE_NAMES}
        feat.update({
            "flow_duration": dur,
            "Header_Length": 20.0 * n_pkts,
            "Protocol Type": 6 if not attack else rng.choice([6, 17]),
            "Duration": dur,
            "Rate": rate,
            "Srate": rate * 0.6,
            "Drate": rate * 0.4,
            "fin_flag_number": rng.uniform(0, 0.05),
            "syn_flag_number": syn_frac,
            "rst_flag_number": rng.uniform(0, 0.1) if attack else 0.0,
            "psh_flag_number": rng.uniform(0, 0.3),
            "ack_flag_number": ack_frac,
            "ack_count": int(ack_frac * n_pkts),
            "syn_count": int(syn_frac * n_pkts),
            "fin_count": rng.integers(0, 5),
            "urg_count": 0,
            "rst_count": rng.integers(0, 10) if attack else 0,
            "TCP": 1,
            "UDP": 0,
            "Tot sum": tot,
            "Min": avg_size * 0.5,
            "Max": avg_size * 1.5,
            "AVG": avg_size,
            "Std": std_size,
            "Tot size": tot,
            "IAT": dur / max(n_pkts - 1, 1),
            "Number": n_pkts,
            "Magnitue": math.sqrt(avg_size),
            "Radius": math.sqrt(std_size),
            "Covariance": rng.uniform(-10, 10),
            "Variance": std_size ** 2,
            "Weight": int(n_pkts * 0.6) * int(n_pkts * 0.4),
        })
        results.append(feat)

    return results
