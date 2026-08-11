import socket
import threading

from core.config import CONFIG

from .common import log


DRONE_HOST = str(CONFIG.get("DRONE_HOST"))
DRONE_PLAIN_RX_PORT = int(CONFIG.get("DRONE_PLAINTEXT_RX", 47004))
DRONE_PLAIN_TX_PORT = int(CONFIG.get("DRONE_PLAINTEXT_TX", 47003))


class UdpEchoServer:
    def __init__(self, bind_host: str = DRONE_HOST, rx_port: int = DRONE_PLAIN_RX_PORT, tx_port: int = DRONE_PLAIN_TX_PORT):
        self.bind_host = bind_host
        self.rx_port = int(rx_port)
        self.tx_port = int(tx_port)
        self.rx_sock = None
        self.tx_sock = None
        self.running = False
        self.thread = None
        self.rx_count = 0
        self.tx_count = 0
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.lock = threading.Lock()

    def start(self):
        if self.running:
            return
        self.rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        self.rx_sock.bind((self.bind_host, self.rx_port))
        self.rx_sock.settimeout(1.0)
        self.tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.tx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        self.running = True
        self.thread = threading.Thread(target=self._echo_loop, daemon=True)
        self.thread.start()
        log(f"Echo server listening on {self.bind_host}:{self.rx_port}")

    def _echo_loop(self):
        while self.running:
            try:
                data, _addr = self.rx_sock.recvfrom(65535)
                with self.lock:
                    self.rx_count += 1
                    self.rx_bytes += len(data)
                self.tx_sock.sendto(data, (self.bind_host, self.tx_port))
                with self.lock:
                    self.tx_count += 1
                    self.tx_bytes += len(data)
            except socket.timeout:
                continue
            except Exception as exc:
                if self.running:
                    log(f"Echo error: {exc}")

    def get_stats(self):
        with self.lock:
            return {
                "rx_count": self.rx_count,
                "tx_count": self.tx_count,
                "rx_bytes": self.rx_bytes,
                "tx_bytes": self.tx_bytes,
            }

    def reset_stats(self):
        with self.lock:
            self.rx_count = 0
            self.tx_count = 0
            self.rx_bytes = 0
            self.tx_bytes = 0

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.rx_sock:
            self.rx_sock.close()
        if self.tx_sock:
            self.tx_sock.close()


