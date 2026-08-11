import json
import socket
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sscheduler.control_security import (
    compute_request_mac,
    compute_telemetry_mac,
    create_nonce_hex,
    verify_telemetry_mac,
)
from sscheduler.control_server_base import ControlServerBase


class DummyProxy:
    def __init__(self):
        self.current_suite = None
        self.current_aead = None
        self._running = False

    def start(self, suite, aead_token=None):
        self.current_suite = suite
        self.current_aead = aead_token
        self._running = True
        return True

    def stop(self):
        self._running = False

    def is_running(self):
        return self._running


def _rpc(host: str, port: int, request: dict, *, timeout: float = 2.0) -> dict:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8").strip() or "{}")


class TestSschedulerControlAuth(unittest.TestCase):

    def setUp(self):
        self.proxy = DummyProxy()
        self.key = b"k" * 32
        self.srv = ControlServerBase(
            self.proxy,
            host="127.0.0.1",
            port=0,
            suites=[],
            allowed_senders=["127.0.0.1"],
            auth_key=self.key,
            require_auth=True,
        )
        self.srv.start()
        self.assertIsNotNone(self.srv.bound_port)
        time.sleep(0.05)

    def tearDown(self):
        self.srv.stop()

    def test_ping_allowed_without_auth(self):
        resp = _rpc("127.0.0.1", self.srv.bound_port, {"cmd": "ping"})
        self.assertEqual(resp.get("status"), "ok")
        self.assertEqual(resp.get("message"), "pong")

    def test_requires_auth_for_non_ping(self):
        resp = _rpc("127.0.0.1", self.srv.bound_port, {"cmd": "status"})
        self.assertEqual(resp.get("status"), "error")
        self.assertIn(resp.get("message"), {"auth_required", "auth_failed"})

    def test_accepts_valid_mac_and_rejects_replay(self):
        params = {}
        nonce = create_nonce_hex()
        mac = compute_request_mac(cmd="status", params=params, nonce_hex=nonce, key=self.key)

        ok_resp = _rpc(
            "127.0.0.1",
            self.srv.bound_port,
            {"cmd": "status", "nonce": nonce, "mac": mac},
        )
        self.assertEqual(ok_resp.get("status"), "ok")

        replay_resp = _rpc(
            "127.0.0.1",
            self.srv.bound_port,
            {"cmd": "status", "nonce": nonce, "mac": mac},
        )
        self.assertEqual(replay_resp.get("status"), "error")
        self.assertEqual(replay_resp.get("message"), "replay")

    def test_sender_allowlist_blocks_unknown_ip(self):
        proxy = DummyProxy()
        srv = ControlServerBase(
            proxy,
            host="127.0.0.1",
            port=0,
            suites=[],
            allowed_senders=["192.0.2.123"],
            auth_key=b"k" * 32,
            require_auth=True,
        )
        srv.start()
        self.assertIsNotNone(srv.bound_port)

        time.sleep(0.05)

        try:
            resp = _rpc("127.0.0.1", srv.bound_port, {"cmd": "ping"})
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            resp = {"status": "error", "message": "sender_not_allowed"}

        self.assertEqual(resp.get("status"), "error")
        self.assertEqual(resp.get("message"), "sender_not_allowed")

        srv.stop()

    def test_telemetry_mac_detects_tampering(self):
        key = b"t" * 32
        envelope = {
            "schema": "uav.pqc.telemetry.batch.v1",
            "batch_wall_ns": 123456789,
            "count": 1,
            "samples": [{"rx_pps": 120.0, "gap_ms": 3.0}],
        }
        nonce = create_nonce_hex()
        mac = compute_telemetry_mac(envelope=envelope, nonce_hex=nonce, key=key)

        self.assertTrue(verify_telemetry_mac(envelope=envelope, nonce_hex=nonce, mac_hex=mac, key=key))

        tampered = {**envelope, "count": 2}
        self.assertFalse(verify_telemetry_mac(envelope=tampered, nonce_hex=nonce, mac_hex=mac, key=key))

    def test_telemetry_mac_is_nonce_bound(self):
        key = b"n" * 32
        envelope = {
            "schema": "uav.pqc.telemetry.batch.v1",
            "batch_wall_ns": 999,
            "count": 0,
            "samples": [],
        }
        nonce_a = create_nonce_hex()
        nonce_b = create_nonce_hex()

        mac_a = compute_telemetry_mac(envelope=envelope, nonce_hex=nonce_a, key=key)
        mac_b = compute_telemetry_mac(envelope=envelope, nonce_hex=nonce_b, key=key)

        self.assertNotEqual(mac_a, mac_b)


if __name__ == "__main__":
    unittest.main()

