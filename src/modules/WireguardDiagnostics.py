"""
WireGuard Diagnostics — collects interface, peer, and route data
for the live diagnostic terminal.
"""

import subprocess
import re
import time
import json
import threading
from datetime import datetime


class DiagnosticsCollector:
    """Collects raw diagnostic data from system commands."""

    def collect_interface_info(self, interface: str) -> dict | None:
        """Collect interface state from `ip address show <iface>`."""
        try:
            output = subprocess.check_output(
                f"ip address show {interface}",
                shell=True, stderr=subprocess.STDOUT
            ).decode("utf-8")
        except subprocess.CalledProcessError:
            return None

        status = "up" if "UP" in output.split("\n")[0] else "down"

        mtu_match = re.search(r"mtu\s+(\d+)", output)
        mtu = int(mtu_match.group(1)) if mtu_match else None

        addr_match = re.search(r"inet\s+(\S+)", output)
        address = addr_match.group(1) if addr_match else None

        fwmark = None

        return {
            "status": status,
            "mtu": mtu,
            "address": address,
            "fwmark": fwmark,
        }
