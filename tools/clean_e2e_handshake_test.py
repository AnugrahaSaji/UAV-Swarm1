import os
import sys
import socket
import threading
import time

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set valid 32-byte (64 hex char) PSK
TEST_PSK = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
os.environ["DRONE_PSK"] = TEST_PSK

from core.handshake import (
    server_gcs_handshake,
    client_drone_handshake,
    Signature,
    KeyEncapsulation,
    CONFIG,
)
from core.suites import SUITES

CONFIG["DRONE_PSK"] = TEST_PSK
CONFIG["MAV_AUTH_KEY"] = TEST_PSK

def main():
    print("=== Clean PQC End-to-End Handshake Test ===")
    print(f"DRONE_PSK set ({len(TEST_PSK)} hex chars)")
    
    suite_id = "cs-mlkem768-mldsa65"
    if suite_id in SUITES:
        suite = dict(SUITES[suite_id])
        suite["suite_id"] = suite_id
    else:
        suite = {
            "suite_id": suite_id,
            "kem_name": "ML-KEM-768",
            "sig_name": "ML-DSA-65",
        }
    print(f"Cipher suite: {suite}")

    # Generate ONE GCS keypair
    print("Generating GCS ML-DSA-65 keypair...")
    gcs_sig_secret = Signature("ML-DSA-65")
    gcs_sig_pub = gcs_sig_secret.generate_keypair()
    print(f"GCS Public Key size: {len(gcs_sig_pub)} bytes")
    assert len(gcs_sig_pub) == 1952, f"Expected 1952 bytes, got {len(gcs_sig_pub)}"

    # Setup local socket pair for loopback test
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    port = server_sock.getsockname()[1]
    server_sock.listen(1)

    server_result = {}
    client_result = {}
    server_error = None
    client_error = None

    def run_server():
        nonlocal server_result, server_error
        try:
            conn, addr = server_sock.accept()
            res = server_gcs_handshake(conn, suite, gcs_sig_secret, timeout=5.0)
            server_result["key_recv"] = res[0]
            server_result["key_send"] = res[1]
            server_result["session_id"] = res[4]
            conn.close()
        except Exception as e:
            server_error = e
        finally:
            server_sock.close()

    def run_client():
        nonlocal client_result, client_error
        try:
            client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_sock.connect(("127.0.0.1", port))
            res = client_drone_handshake(client_sock, suite, gcs_sig_pub, timeout=5.0)
            client_result["key_send"] = res[0]
            client_result["key_recv"] = res[1]
            client_result["session_id"] = res[4]
            client_sock.close()
        except Exception as e:
            client_error = e

    server_thread = threading.Thread(target=run_server)
    client_thread = threading.Thread(target=run_client)

    server_thread.start()
    time.sleep(0.1)
    client_thread.start()

    server_thread.join(timeout=10)
    client_thread.join(timeout=10)

    if server_error:
        print(f"SERVER ERROR: {server_error}")
        raise server_error
    if client_error:
        print(f"CLIENT ERROR: {client_error}")
        raise client_error

    print("\n--- Handshake Results ---")
    print(f"GCS send key length: {len(server_result['key_send'])} bytes")
    print(f"GCS recv key length: {len(server_result['key_recv'])} bytes")
    print(f"Drone send key length: {len(client_result['key_send'])} bytes")
    print(f"Drone recv key length: {len(client_result['key_recv'])} bytes")

    # Verify symmetry: GCS send key == Drone recv key, GCS recv key == Drone send key
    assert server_result["key_send"] == client_result["key_recv"], "Key mismatch: GCS send != Drone recv"
    assert server_result["key_recv"] == client_result["key_send"], "Key mismatch: GCS recv != Drone send"
    assert server_result["session_id"] == client_result["session_id"], "Session ID mismatch"

    print("\nSUCCESS: End-to-end PQC Handshake verified! (Signature verification, KEM encaps/decaps, PSK auth tag, key confirmation all passed).")

if __name__ == "__main__":
    main()
