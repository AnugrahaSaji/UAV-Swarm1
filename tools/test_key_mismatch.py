import os
import sys
import socket
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

TEST_PSK = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
os.environ["DRONE_PSK"] = TEST_PSK

from core.handshake import (
    server_gcs_handshake,
    client_drone_handshake,
    Signature,
    HandshakeVerifyError,
    CONFIG,
)
from core.suites import SUITES

CONFIG["DRONE_PSK"] = TEST_PSK
CONFIG["MAV_AUTH_KEY"] = TEST_PSK

def main():
    print("=== Testing Mismatched Identity Public Key (Simulating --ephemeral rotation mismatch) ===")
    suite_id = "cs-mlkem768-mldsa65"
    suite = dict(SUITES[suite_id])
    suite["suite_id"] = suite_id

    # GCS active keypair A
    gcs_active_secret = Signature("ML-DSA-65")
    _ = gcs_active_secret.generate_keypair()

    # Yesterday's / stale public key B given to Pi
    stale_secret_B = Signature("ML-DSA-65")
    stale_pub_B = stale_secret_B.generate_keypair()

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    port = server_sock.getsockname()[1]
    server_sock.listen(1)

    client_error = None

    def run_server():
        try:
            conn, addr = server_sock.accept()
            _ = server_gcs_handshake(conn, suite, gcs_active_secret, timeout=5.0)
            conn.close()
        except Exception:
            pass
        finally:
            server_sock.close()

    def run_client():
        nonlocal client_error
        try:
            client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_sock.connect(("127.0.0.1", port))
            _ = client_drone_handshake(client_sock, suite, stale_pub_B, timeout=5.0)
            client_sock.close()
        except Exception as e:
            client_error = e

    t_srv = threading.Thread(target=run_server)
    t_cli = threading.Thread(target=run_client)
    t_srv.start()
    time.sleep(0.1)
    t_cli.start()
    t_srv.join()
    t_cli.join()

    print(f"Captured Client Error: {type(client_error).__name__}: {client_error}")
    assert isinstance(client_error, HandshakeVerifyError), f"Expected HandshakeVerifyError, got {type(client_error)}"
    assert "bad signature" in str(client_error), f"Expected 'bad signature' error message, got '{client_error}'"
    print("\nSUCCESS: Identity key mismatch reproduces exact 'bad signature' failure as predicted!")

if __name__ == "__main__":
    main()
