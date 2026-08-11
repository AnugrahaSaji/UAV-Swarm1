import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from sscheduler.sdrone_bench import (  # noqa: E402
    _is_live_data_flow_ready,
    _select_clock_sync_sample,
)


def test_select_clock_sync_sample_uses_median_offset_and_best_rtt():
    selected = _select_clock_sync_sample(
        [
            {"offset": 0.101, "rtt_ms": 8.4},
            {"offset": 0.097, "rtt_ms": 3.2},
            {"offset": 0.115, "rtt_ms": 5.6},
        ]
    )
    assert selected is not None
    assert round(selected["offset_ms"], 3) == 101.0
    assert round(selected["rtt_ms_best"], 3) == 3.2
    assert selected["samples"] == 3


def test_live_data_flow_ready_requires_local_and_gcs_activity():
    local = {"ptx_in": 48, "enc_out": 48}
    gcs = {
        "mavlink_validation": {"total_msgs_received": 64},
        "link_status": {"stream_active": True, "heartbeat_present": True},
    }
    assert _is_live_data_flow_ready(local, gcs)


def test_live_data_flow_ready_rejects_idle_gcs_status():
    local = {"ptx_in": 96, "enc_out": 96}
    gcs = {
        "mavlink_validation": {"total_msgs_received": 0},
        "link_status": {"stream_active": False, "heartbeat_present": False},
    }
    assert not _is_live_data_flow_ready(local, gcs)
