"""
TelemetryWindow: bounded sliding-window of telemetry samples (monotonic-time based)

Maintains O(1) amortized operations using collections.deque. Exposes add() and
summarize(now_mono) which returns derived statistics required by DecisionContext.

All computations are bounded and non-blocking.
"""
from collections import deque
from threading import Lock
import statistics
from typing import Deque, Dict, List, Tuple, Any, Optional


class TelemetryWindow:
    """
    Bounded sliding window for telemetry analysis.
    
    Thread-safe. All operations are O(1) amortized or O(n) where n is window size.
    Window size is bounded by time (window_s) not count, with implicit max ~500 samples.
    """
    
    # Expected telemetry rate for confidence calculation
    EXPECTED_HZ = 5.0
    MAX_SAMPLES = 500  # Hard cap to bound memory
    
    def __init__(self, window_s: float = 5.0):
        self.window_s = float(window_s)
        # store tuples: (mono_s, seq, cpu_pct, mem_pct, raw_packet)
        self._dq: Deque[Tuple[float, int, float, float, Dict[str, Any]]] = deque(maxlen=self.MAX_SAMPLES)
        self.lock = Lock()
        # Track last received heartbeat age from telemetry
        self._last_heartbeat_age_ms: float = 0.0
        self._last_failsafe: bool = False
        self._last_armed: bool = False

    def add(self, mono_s: float, packet: Dict[str, Any]) -> None:
        """Add sample with monotonic timestamp and packet dict. Non-blocking."""
        seq = packet.get("seq", 0)
        
        # Extract metrics safely
        cpu = 0.0
        mem = 0.0
        try:
            metrics = packet.get("metrics", {})
            sys_metrics = metrics.get("sys", {})
            cpu = float(sys_metrics.get("cpu_pct", 0.0))
            mem = float(sys_metrics.get("mem_pct", 0.0))
            
            # Extract flight state if present
            flight = metrics.get("flight", {})
            self._last_heartbeat_age_ms = float(flight.get("heartbeat_age_ms", 0.0))
            self._last_failsafe = bool(flight.get("failsafe", False))
            self._last_armed = bool(flight.get("armed", False))
        except Exception:
            pass

        with self.lock:
            self._dq.append((mono_s, int(seq), cpu, mem, packet))
            self._prune_locked(mono_s)

    def _prune_locked(self, now_mono: float) -> None:
        """Remove samples older than window_s. Must hold lock."""
        cutoff = now_mono - self.window_s
        while self._dq and self._dq[0][0] < cutoff:
            self._dq.popleft()

    def get_confidence(self, now_mono: float) -> float:
        """Compute confidence as received_samples / expected_samples."""
        with self.lock:
            self._prune_locked(now_mono)
            n = len(self._dq)
        
        expected = self.EXPECTED_HZ * self.window_s
        return min(1.0, n / expected) if expected > 0 else 0.0

    def get_flight_state(self) -> Dict[str, Any]:
        """Return last known flight state from telemetry."""
        return {
            "heartbeat_age_ms": self._last_heartbeat_age_ms,
            "failsafe": self._last_failsafe,
            "armed": self._last_armed,
        }

    def summarize(self, now_mono: float) -> Dict[str, Any]:
        """
        Return derived statistics for current window (best-effort).
        
        All computations bounded by MAX_SAMPLES and non-blocking after lock acquisition.
        """
        with self.lock:
            self._prune_locked(now_mono)
            n = len(self._dq)
            if n == 0:
                return {
                    "sample_count": 0,
                    "telemetry_age_ms": -1.0,
                    "rx_pps_median": 0.0,
                    "silence_max_ms": -1.0,
                    "gap_p95_ms": 0.0,
                    "jitter_ms": 0.0,
                    "gcs_cpu_median": 0.0,
                    "gcs_cpu_p95": 0.0,
                    "gcs_mem_median": 0.0,
                    "last_seq": 0,
                    "confidence": 0.0,
                    "missing_seq_count": 0,
                    "out_of_order_count": 0,
                }

            # Extract arrays (bounded by MAX_SAMPLES)
            monos = [t[0] for t in self._dq]
            seqs = [t[1] for t in self._dq]
            cpus = [t[2] for t in self._dq]
            mems = [t[3] for t in self._dq]

        # Compute stats outside lock
        last_mono = monos[-1]
        telemetry_age_ms = max(0.0, (now_mono - last_mono) * 1000.0)

        # Inter-arrival gaps in ms
        gaps_ms: List[float] = []
        for i in range(1, n):
            g = (monos[i] - monos[i - 1]) * 1000.0
            gaps_ms.append(g)

        # Packets per second (median of instantaneous rates)
        pps_list: List[float] = []
        for g in gaps_ms:
            if g > 0:
                pps_list.append(1000.0 / g)

        if pps_list:
            rx_pps_median = float(statistics.median(pps_list))
        elif n > 1 and monos[-1] > monos[0]:
            rx_pps_median = (n - 1) / (monos[-1] - monos[0])
        else:
            rx_pps_median = 0.0

        # Silence: max of current age and largest gap
        silence_max_ms = telemetry_age_ms
        if gaps_ms:
            silence_max_ms = max(silence_max_ms, max(gaps_ms))

        # Gap p95 and jitter
        gap_p95_ms = 0.0
        jitter_ms = 0.0
        if gaps_ms:
            gs_sorted = sorted(gaps_ms)
            idx = min(int(len(gs_sorted) * 0.95), len(gs_sorted) - 1)
            gap_p95_ms = gs_sorted[idx]
            mean_gap = sum(gs_sorted) / len(gs_sorted)
            jitter_ms = float(statistics.median([abs(g - mean_gap) for g in gs_sorted]))

        # CPU stats
        gcs_cpu_median = float(statistics.median(cpus)) if cpus else 0.0
        cpu_sorted = sorted(cpus)
        idx_cpu = min(int(len(cpu_sorted) * 0.95), len(cpu_sorted) - 1)
        gcs_cpu_p95 = float(cpu_sorted[idx_cpu]) if cpu_sorted else 0.0

        # Memory stats
        gcs_mem_median = float(statistics.median(mems)) if mems else 0.0

        # Sequence analysis (missing and out-of-order)
        missing_seq_count = 0
        out_of_order_count = 0
        if len(seqs) > 1:
            for i in range(1, len(seqs)):
                diff = seqs[i] - seqs[i - 1]
                if diff > 1:
                    missing_seq_count += diff - 1
                elif diff < 0:
                    out_of_order_count += 1

        # Confidence
        expected = self.EXPECTED_HZ * self.window_s
        confidence = min(1.0, n / expected) if expected > 0 else 0.0

        return {
            "sample_count": n,
            "telemetry_age_ms": round(telemetry_age_ms, 1),
            "rx_pps_median": round(rx_pps_median, 2),
            "silence_max_ms": round(silence_max_ms, 1),
            "gap_p95_ms": round(gap_p95_ms, 1),
            "jitter_ms": round(jitter_ms, 1),
            "gcs_cpu_median": round(gcs_cpu_median, 1),
            "gcs_cpu_p95": round(gcs_cpu_p95, 1),
            "gcs_mem_median": round(gcs_mem_median, 1),
            "last_seq": seqs[-1],
            "confidence": round(confidence, 3),
            "missing_seq_count": missing_seq_count,
            "out_of_order_count": out_of_order_count,
        }
