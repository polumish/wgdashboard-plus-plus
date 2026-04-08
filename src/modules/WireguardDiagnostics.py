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

    def collect_peers(self, interface: str, protocol: str = "wg") -> tuple[dict | None, list]:
        """Collect peer data from `wg show <iface>`. Returns (interface_data, peers_list)."""
        try:
            output = subprocess.check_output(
                f"{protocol} show {interface}",
                shell=True, stderr=subprocess.STDOUT
            ).decode("utf-8")
        except subprocess.CalledProcessError:
            return None, []

        iface_data = {}
        peers = []
        current_peer = None

        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("public key:"):
                iface_data["publicKey"] = line.split(": ", 1)[1]
            elif line.startswith("listening port:"):
                iface_data["listenPort"] = int(line.split(": ", 1)[1])
            elif line.startswith("fwmark:"):
                iface_data["fwmark"] = line.split(": ", 1)[1]
            elif line.startswith("peer:"):
                if current_peer:
                    peers.append(current_peer)
                current_peer = {
                    "publicKey": line.split(": ", 1)[1],
                    "endpoint": None,
                    "allowedIps": [],
                    "latestHandshake": None,
                    "transferRx": 0,
                    "transferTx": 0,
                    "status": "inactive",
                }
            elif current_peer and line.startswith("endpoint:"):
                current_peer["endpoint"] = line.split(": ", 1)[1]
            elif current_peer and line.startswith("allowed ips:"):
                current_peer["allowedIps"] = [
                    ip.strip() for ip in line.split(": ", 1)[1].split(",")
                ]
            elif current_peer and line.startswith("latest handshake:"):
                handshake_str = line.split(": ", 1)[1]
                current_peer["latestHandshake"] = handshake_str
                current_peer["status"] = self._handshake_to_status(handshake_str)
            elif current_peer and line.startswith("transfer:"):
                parts = line.split(": ", 1)[1]
                rx_match = re.match(r"([\d.]+)\s+(\S+)\s+received", parts)
                tx_match = re.search(r"([\d.]+)\s+(\S+)\s+sent", parts)
                if rx_match:
                    current_peer["transferRx"] = self._parse_transfer(
                        float(rx_match.group(1)), rx_match.group(2)
                    )
                if tx_match:
                    current_peer["transferTx"] = self._parse_transfer(
                        float(tx_match.group(1)), tx_match.group(2)
                    )

        if current_peer:
            peers.append(current_peer)

        return iface_data, peers

    @staticmethod
    def _handshake_to_status(handshake_str: str) -> str:
        """Determine peer status from handshake string."""
        if not handshake_str or handshake_str == "No Handshake":
            return "inactive"
        match = re.search(r"(\d+)\s+(second|minute|hour|day)", handshake_str)
        if not match:
            return "inactive"
        value = int(match.group(1))
        unit = match.group(2)
        seconds = value
        if unit == "minute":
            seconds = value * 60
        elif unit == "hour":
            seconds = value * 3600
        elif unit == "day":
            seconds = value * 86400
        return "online" if seconds < 120 else "offline"

    @staticmethod
    def _parse_transfer(value: float, unit: str) -> int:
        """Convert transfer value+unit to bytes."""
        multipliers = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}
        return int(value * multipliers.get(unit, 1))

    def collect_routes(self, interface: str) -> list:
        """Collect system routes from `ip route show dev <iface>`."""
        try:
            output = subprocess.check_output(
                f"ip route show dev {interface}",
                shell=True, stderr=subprocess.STDOUT
            ).decode("utf-8")
        except subprocess.CalledProcessError:
            return []

        routes = []
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split()
            destination = parts[0]

            gateway = "kernel"
            metric = 0

            if "via" in parts:
                via_idx = parts.index("via")
                gateway = parts[via_idx + 1]
            if "metric" in parts:
                m_idx = parts.index("metric")
                metric = int(parts[m_idx + 1])

            routes.append({
                "destination": destination,
                "gateway": gateway,
                "metric": metric,
            })

        return routes

    def cross_reference(self, routes: list, peers: list, interface_subnet: str) -> tuple[list, list]:
        """Cross-reference routes with peers. Returns (annotated_routes, warnings)."""
        warnings = []

        # Build gateway→peer lookup from AllowedIPs
        gw_to_peer = {}
        all_allowed_destinations = set()
        for peer in peers:
            for aip in peer.get("allowedIps", []):
                all_allowed_destinations.add(aip)
                ip = aip.split("/")[0]
                gw_to_peer[ip] = peer

        annotated = []
        routed_destinations = set()

        for route in routes:
            entry = dict(route)
            routed_destinations.add(route["destination"])

            if route["gateway"] == "kernel":
                entry["peer"] = None
                entry["status"] = "ok"
                entry["statusText"] = "interface subnet"
            elif route["gateway"] in gw_to_peer:
                peer = gw_to_peer[route["gateway"]]
                name = peer.get("name", peer["publicKey"][:12])
                entry["peer"] = name
                if peer["status"] == "online":
                    entry["status"] = "ok"
                    entry["statusText"] = "AllowedIPs match"
                elif peer["status"] == "offline":
                    entry["status"] = "warning"
                    entry["statusText"] = "peer offline"
                    warnings.append({
                        "type": "peer_offline",
                        "target": name,
                        "message": f"{route['destination']} → {name} — route exists but peer offline",
                    })
                else:
                    entry["status"] = "warning"
                    entry["statusText"] = "peer inactive"
                    warnings.append({
                        "type": "peer_inactive",
                        "target": name,
                        "message": f"{route['destination']} → {name} — route exists but peer never connected",
                    })
            else:
                entry["peer"] = None
                entry["status"] = "warning"
                entry["statusText"] = "orphan route"
                warnings.append({
                    "type": "orphan_route",
                    "target": route["destination"],
                    "message": f"{route['destination']} — route via this interface but no matching peer",
                })

            annotated.append(entry)

        # Check for AllowedIPs without system routes (skip /32 peer addresses and interface subnet)
        for peer in peers:
            name = peer.get("name", peer["publicKey"][:12])
            for aip in peer.get("allowedIps", []):
                if aip.endswith("/32"):
                    continue
                if aip == interface_subnet:
                    continue
                if aip not in routed_destinations:
                    warnings.append({
                        "type": "missing_route",
                        "target": aip,
                        "message": f"{aip} in AllowedIPs of {name} but no system route found",
                    })

        return annotated, warnings

    def build_snapshot(self, interface: str, protocol: str = "wg", peer_names: dict = None) -> dict | None:
        """Build complete diagnostics snapshot for one interface."""
        if peer_names is None:
            peer_names = {}

        info = self.collect_interface_info(interface)
        if info is None:
            return None

        iface_data, peers = self.collect_peers(interface, protocol)
        if iface_data is None:
            iface_data = {}

        # Resolve peer names
        for peer in peers:
            peer["name"] = peer_names.get(peer["publicKey"], peer["publicKey"][:12] + "…")

        routes = self.collect_routes(interface)
        annotated_routes, warnings = self.cross_reference(
            routes, peers, info.get("address", "")
        )

        # Add peer-level warnings (offline peers)
        for peer in peers:
            if peer["status"] == "offline":
                warnings.append({
                    "type": "peer_offline",
                    "target": peer["name"],
                    "message": f"{peer['name']} — last handshake: {peer['latestHandshake']} (threshold: 2m)",
                })

        return {
            "status": info["status"],
            "address": info["address"],
            "mtu": info["mtu"],
            "fwmark": iface_data.get("fwmark"),
            "listenPort": iface_data.get("listenPort"),
            "publicKey": iface_data.get("publicKey"),
            "peers": peers,
            "routes": annotated_routes,
            "warnings": warnings,
            "timestamp": int(time.time()),
        }


class DiagnosticsMonitor:
    """Background monitor that tracks state changes and notifies SSE subscribers."""

    def __init__(self):
        self._collector = DiagnosticsCollector()
        self._last_state = {}  # interface_name → last JSON string
        self._subscribers = []  # list of (queue, interfaces_filter)
        self._lock = threading.Lock()
        self._running = False

    def subscribe(self, interfaces: list | None = None):
        """Subscribe to diagnostics updates. Returns a queue that receives JSON strings."""
        import queue
        q = queue.Queue(maxsize=50)
        with self._lock:
            self._subscribers.append((q, interfaces))
        return q

    def unsubscribe(self, q):
        """Remove a subscriber queue."""
        with self._lock:
            self._subscribers = [(sq, f) for sq, f in self._subscribers if sq is not q]

    def start(self, get_configurations, app_logger):
        """Start the background monitor thread."""
        self._get_configurations = get_configurations
        self._logger = app_logger
        self._running = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()
        self._logger.info("DiagnosticsMonitor thread started")

    def _get_peer_names(self, config) -> dict:
        """Extract public_key → name mapping from a WireguardConfiguration's peers."""
        names = {}
        try:
            for peer in config.Peers:
                if hasattr(peer, 'name') and peer.name:
                    names[peer.id] = peer.name
                elif hasattr(peer, 'DNS') and peer.DNS:
                    names[peer.id] = peer.DNS
        except Exception:
            pass
        return names

    def _monitor_loop(self):
        """Main loop: collect snapshots, push changes to subscribers."""
        import queue as queue_module
        while self._running:
            try:
                configurations = self._get_configurations()
                full_snapshot = {}

                for name, config in configurations.items():
                    protocol = getattr(config, 'Protocol', 'wg')
                    peer_names = self._get_peer_names(config)
                    snapshot = self._collector.build_snapshot(name, protocol, peer_names)
                    if snapshot:
                        full_snapshot[name] = snapshot

                with self._lock:
                    for name, snap in full_snapshot.items():
                        snap_json = json.dumps(snap, sort_keys=True)
                        if self._last_state.get(name) != snap_json:
                            self._last_state[name] = snap_json
                            for q, iface_filter in self._subscribers:
                                if iface_filter is None or name in iface_filter:
                                    try:
                                        payload = json.dumps({"interfaces": {name: snap}, "timestamp": int(time.time())})
                                        q.put_nowait(payload)
                                    except queue_module.Full:
                                        pass
            except Exception as e:
                if self._logger:
                    self._logger.error(f"DiagnosticsMonitor error: {e}")

            time.sleep(1)
