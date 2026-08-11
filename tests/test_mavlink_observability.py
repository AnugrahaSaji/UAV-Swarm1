import json
import time
from pathlib import Path

from core.mavlink_collector import MavLinkMetricsCollector
from sscheduler.sgcs_bench import GcsBenchmarkServer


class FakeMavLinkMessage:
    def __init__(
        self,
        msg_type,
        msg_id,
        *,
        fields=None,
        seq=0,
        sysid=1,
        compid=1,
        payload=b"x",
    ):
        self._msg_type = msg_type
        self._msg_id = msg_id
        self._fields = dict(fields or {})
        self._seq = seq
        self._sysid = sysid
        self._compid = compid
        self._payload = payload
        for key, value in self._fields.items():
            setattr(self, key, value)

    def get_type(self):
        return self._msg_type

    def get_msgId(self):
        return self._msg_id

    def get_srcSystem(self):
        return self._sysid

    def get_srcComponent(self):
        return self._compid

    def get_payload(self):
        return self._payload

    def get_seq(self):
        return self._seq

    def to_dict(self):
        return {"mavpackettype": self._msg_type, **self._fields}


def test_mavlink_collector_exports_recent_messages_and_link_state():
    collector = MavLinkMetricsCollector(role="gcs")
    collector._start_time_mono = time.monotonic() - 2.0

    collector._handle_message(
        FakeMavLinkMessage(
            "HEARTBEAT",
            0,
            fields={"custom_mode": 4, "base_mode": 128, "system_status": 4},
            seq=10,
        ),
        time.monotonic() - 0.15,
        time.time() - 0.15,
    )
    collector._handle_message(
        FakeMavLinkMessage(
            "SYS_STATUS",
            1,
            fields={
                "battery_remaining": 87,
                "voltage_battery": 11800,
                "current_battery": 230,
                "load": 420,
            },
            seq=11,
        ),
        time.monotonic() - 0.10,
        time.time() - 0.10,
    )
    collector._handle_message(
        FakeMavLinkMessage(
            "STATUSTEXT",
            253,
            fields={"severity": 4, "text": "GPS lock acquired"},
            seq=12,
        ),
        time.monotonic() - 0.05,
        time.time() - 0.05,
    )

    metrics = collector.get_metrics()

    assert metrics["link_status"]["state"] == "healthy"
    assert metrics["link_status"]["heartbeat_present"] is True
    assert metrics["flight_controller"]["fc_battery_remaining_percent"] == 87.0
    assert metrics["recent_messages"][-1]["type"] == "STATUSTEXT"
    assert metrics["recent_messages"][-1]["fields"]["text"] == "GPS lock acquired"
    assert metrics["recent_statustext"][-1]["text"] == "GPS lock acquired"
    assert any(item["type"] == "HEARTBEAT" for item in metrics["top_message_types"])


def test_mavlink_live_export_writes_jsonl_snapshots(tmp_path: Path):
    collector = MavLinkMetricsCollector(role="gcs")
    collector._start_time_mono = time.monotonic() - 1.0
    output_path = tmp_path / "mavlink_live.jsonl"

    collector.start_live_export(
        str(output_path),
        interval_s=0.1,
        recent_messages=4,
        context={"suite": "cs-mlkem512-mldsa44"},
    )
    collector._handle_message(
        FakeMavLinkMessage(
            "HEARTBEAT",
            0,
            fields={"custom_mode": 7, "base_mode": 128, "system_status": 4},
            seq=21,
        ),
        time.monotonic(),
        time.time(),
    )
    time.sleep(0.2)
    collector.stop_live_export()

    lines = [line for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    final_snapshot = json.loads(lines[-1])
    assert final_snapshot["phase"] == "final"
    assert final_snapshot["context"]["suite"] == "cs-mlkem512-mldsa44"
    assert final_snapshot["link_status"]["heartbeat_present"] is True


def test_gcs_bench_extract_mavlink_reports_keeps_observability():
    raw = {
        "total_msgs_received": 120,
        "seq_gap_count": 2,
        "one_way_latency_avg_ms": 14.2,
        "one_way_latency_p95_ms": 22.1,
        "one_way_latency_valid": True,
        "jitter_avg_ms": 1.7,
        "jitter_p95_ms": 3.4,
        "latency_sample_count": 20,
        "latency_invalid_reason": None,
        "rtt_avg_ms": 28.0,
        "rtt_p95_ms": 34.5,
        "rtt_sample_count": 10,
        "rtt_invalid_reason": None,
        "rtt_valid": True,
        "link_status": {"state": "healthy"},
        "flight_controller": {"fc_mode": "AUTO"},
        "top_message_types": [{"type": "HEARTBEAT", "count_rx": 10}],
        "recent_statustext": [{"text": "Ready"}],
        "recent_messages": [{"type": "HEARTBEAT"}],
    }

    validation, latency, observability = GcsBenchmarkServer._extract_mavlink_reports(raw)

    assert validation == {"total_msgs_received": 120, "seq_gap_count": 2}
    assert latency["rtt_valid"] is True
    assert observability["link_status"]["state"] == "healthy"
    assert observability["recent_messages"][0]["type"] == "HEARTBEAT"
