"""
DDoS Severity Reporter
======================
Writes detection results to /tmp/ddos_severity.json so that the
MDEAS scheduler (DetectorManager / Axis 3) can read detection state
and feed it into orchestration decisions.

The JSON file is atomically replaced on each update using rename.
"""

import json
import os
import tempfile
import time

SEVERITY_PATH = "/tmp/ddos_severity.json"


class SeverityReporter:
    """Write detection verdicts to a shared JSON file."""

    def __init__(self, path: str = SEVERITY_PATH):
        self._path = path

    def report(self, *,
               severity: str,
               tier: str,
               attack_type: str,
               confidence: float,
               details: dict | None = None):
        """Atomically write a severity report.

        Parameters
        ----------
        severity : str
            One of "none", "low", "medium", "high", "critical".
        tier : str
            Which detector tier produced this verdict ("lgbm", "rf", "tst").
        attack_type : str
            Predicted attack class or "BenignTraffic".
        confidence : float
            Model confidence (0.0 – 1.0).
        details : dict, optional
            Extra fields (window stats, feature summary).
        """
        payload = {
            "severity": severity,
            "tier": tier,
            "attack_type": attack_type,
            "confidence": round(confidence, 4),
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        if details:
            payload["details"] = details

        # Atomic write: write to temp file then rename
        dir_name = os.path.dirname(self._path) or "/tmp"
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f)
            os.replace(tmp_path, self._path)
        except OSError:
            # Best-effort cleanup on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    def severity_from_confidence(confidence: float, is_attack: bool) -> str:
        """Map model confidence + attack/benign to a severity level."""
        if not is_attack:
            return "none"
        if confidence >= 0.95:
            return "critical"
        if confidence >= 0.85:
            return "high"
        if confidence >= 0.70:
            return "medium"
        return "low"
