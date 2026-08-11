"""
Settings store for dashboard configuration.
Persists run labels and active run selections to a JSON file.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path("dashboard_settings.json")

# Default run type labels — matches SCENARIO_MAP in ingest.py
RUN_TYPES = {
    "no_ddos":       {"label": "No DDoS (Baseline)", "color": "#3b82f6", "order": 0},
    "ddos_xgboost":  {"label": "DDoS – XGBoost",     "color": "#f59e0b", "order": 1},
    "ddos_txt":      {"label": "DDoS – TXT",          "color": "#ef4444", "order": 2},
}


class SettingsStore:
    """Manages dashboard settings: run labels, active selections."""

    def __init__(self):
        self._settings: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if SETTINGS_FILE.exists():
            try:
                with SETTINGS_FILE.open("r") as f:
                    return json.load(f)
            except Exception:
                logger.warning("Failed to load settings, using defaults")
        return {
            "run_labels": {},       # run_id -> { "label": str, "type": str }
            "active_runs": [],      # ordered list of run_ids currently selected
            "anomaly_thresholds": {
                "handshake_ms_high": 10000,
                "handshake_ms_critical": 30000,
                "packet_loss_warning": 0.01,
                "packet_loss_critical": 0.05,
                "power_deviation_pct": 15,
                "energy_deviation_pct": 20,
            },
        }

    def _save(self):
        with SETTINGS_FILE.open("w") as f:
            json.dump(self._settings, f, indent=2)

    def get_all(self) -> Dict[str, Any]:
        return {**self._settings, "run_types": RUN_TYPES}

    def get_run_label(self, run_id: str) -> Optional[Dict]:
        return self._settings.get("run_labels", {}).get(run_id)

    def set_run_label(self, run_id: str, label: str, run_type: str):
        if "run_labels" not in self._settings:
            self._settings["run_labels"] = {}
        self._settings["run_labels"][run_id] = {
            "label": label,
            "type": run_type,
        }
        self._save()

    def set_active_runs(self, run_ids: List[str]):
        self._settings["active_runs"] = run_ids
        self._save()

    def get_active_runs(self) -> List[str]:
        return self._settings.get("active_runs", [])

    def update_thresholds(self, thresholds: Dict[str, float]):
        if "anomaly_thresholds" not in self._settings:
            self._settings["anomaly_thresholds"] = {}
        self._settings["anomaly_thresholds"].update(thresholds)
        self._save()

    def get_thresholds(self) -> Dict[str, float]:
        return self._settings.get("anomaly_thresholds", {})


# Singleton
_settings_store: Optional[SettingsStore] = None


def get_settings_store() -> SettingsStore:
    global _settings_store
    if _settings_store is None:
        _settings_store = SettingsStore()
    return _settings_store
