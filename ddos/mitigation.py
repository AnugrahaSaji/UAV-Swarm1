#!/usr/bin/env python3
"""
DDoS Mitigation Engine (Axis 3 Companion)
===========================================
Implements high-performance, driver-level and system-level mitigation
inspired by "eBPF-Based Real-Time DDoS Mitigation for IoT Edge" (arXiv:2508.00851).

This module supports:
1. Simulated eBPF/XDP map insertion (tracking dropped packet counts via return codes).
2. Live iptables-based packet dropping on Linux (mimicking XDP_DROP at the kernel boundary).
3. Clean logging and stats output.
"""

import os
import sys
import time
import logging
import platform
import subprocess
from typing import Dict, List, Set, Tuple

logger = logging.getLogger("ddos.mitigation")

# Setup local console logging if run independently
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")


class DDoSMitigator:
    """Manages system-level and eBPF/XDP-simulated packet drops for UAV DDoS protection.

    When an attack is confirmed by the TST (Time Series Transformer) classifier,
    the scheduler or detector triggers DDoSMitigator to blocklist the offending IP/Port.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run or (platform.system().lower() != "linux")
        self.blocked_ips: Set[str] = set()
        self.blocked_ports: Set[int] = set()
        self.ebpf_map_drops: Dict[str, int] = {}  # Simulated eBPF BPF_MAP_TYPE_HASH [IP, Drop Count]

        if self.dry_run:
            logger.info("Initializing DDoS Mitigator in DRY-RUN / SIMULATED mode (Non-Linux or forced).")
        else:
            logger.info("Initializing DDoS Mitigator in LIVE Linux Kernel mode (iptables/eBPF mirroring).")

    def block_ip(self, ip: str, reason: str = "Volumetric DDoS Flood") -> bool:
        """Injects a drop rule for a specific IP into the kernel filtering tables.

        Corresponds to inserting an IP key with a DROP action into the XDP eBPF hash map:
        `bpf_map_update_elem(&blocked_ips_map, &ip, &DROP_ACTION, BPF_ANY);`
        """
        ip = ip.strip()
        if not ip:
            return False

        if ip in self.blocked_ips:
            logger.warning(f"IP {ip} is already blocked.")
            return True

        logger.info(f"🚫 [Mitigation Action] Blocking IP: {ip} | Reason: {reason}")
        self.blocked_ips.add(ip)
        self.ebpf_map_drops[ip] = 0

        if self.dry_run:
            logger.info(f"[eBPF/XDP Simulation] Added {ip} to kernel 'blocked_ips_map'. Return code: XDP_DROP")
            return True

        # Live Linux Action: Insert iptables rule at the top of the INPUT chain
        # (Functionally equivalent to XDP_DROP filtering before socket memory allocation)
        cmd = ["sudo", "iptables", "-I", "INPUT", "1", "-s", ip, "-j", "DROP"]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.info(f"Successfully injected kernel drop rule for {ip} via iptables.")
            return True
        except subprocess.CalledProcessError as err:
            stderr = err.stderr.decode().strip()
            logger.error(f"Failed to inject kernel drop rule for {ip}: {stderr}")
            return False

    def unblock_ip(self, ip: str) -> bool:
        """Removes an IP block rule from the kernel filtering tables.

        Corresponds to deleting the element from the eBPF map:
        `bpf_map_delete_elem(&blocked_ips_map, &ip);`
        """
        ip = ip.strip()
        if ip not in self.blocked_ips:
            logger.warning(f"IP {ip} is not currently blocked.")
            return True

        logger.info(f"🔓 [Mitigation Action] Unblocking IP: {ip}")
        self.blocked_ips.remove(ip)
        self.ebpf_map_drops.pop(ip, None)

        if self.dry_run:
            logger.info(f"[eBPF/XDP Simulation] Removed {ip} from kernel 'blocked_ips_map'. Return code: XDP_PASS")
            return True

        # Live Linux Action: Delete the matching iptables rule
        cmd = ["sudo", "iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.info(f"Successfully removed kernel drop rule for {ip}.")
            return True
        except subprocess.CalledProcessError as err:
            stderr = err.stderr.decode().strip()
            logger.error(f"Failed to remove kernel drop rule for {ip}: {stderr}")
            return False

    def simulate_packet_arrival(self, src_ip: str) -> str:
        """Simulates an incoming packet through the eBPF/XDP hook.

        Returns 'XDP_DROP' or 'XDP_PASS'.
        """
        if src_ip in self.blocked_ips:
            self.ebpf_map_drops[src_ip] += 1
            return "XDP_DROP"
        return "XDP_PASS"

    def get_stats(self) -> Dict[str, Any]:
        """Returns the mitigation database statistics."""
        return {
            "mode": "Simulation/Dry-Run" if self.dry_run else "Kernel-Live",
            "blocked_count": len(self.blocked_ips),
            "blocked_ips": list(self.blocked_ips),
            "simulated_ebpf_drops": self.ebpf_map_drops.copy(),
        }

    def clear_all_blocks(self) -> None:
        """Flushes all blocked rules to restore clean connectivity."""
        if not self.blocked_ips:
            return
        logger.info("Clearing all injected mitigation drop rules...")
        ips_to_clear = list(self.blocked_ips)
        for ip in ips_to_clear:
            self.unblock_ip(ip)


# --- Manual CLI Smoke Test ---
if __name__ == "__main__":
    mitigator = DDoSMitigator()
    mitigator.block_ip("192.168.1.100", reason="Volumetric SYN Flood Anomaly")
    print(f"Stats after block: {mitigator.get_stats()}")

    # Simulate traffic
    print(f"Simulating packet from 192.168.1.100: {mitigator.simulate_packet_arrival('192.168.1.100')}")
    print(f"Simulating packet from 192.168.1.50: {mitigator.simulate_packet_arrival('192.168.1.50')}")
    print(f"Stats after traffic: {mitigator.get_stats()}")

    mitigator.unblock_ip("192.168.1.100")
    print(f"Stats after clear: {mitigator.get_stats()}")
