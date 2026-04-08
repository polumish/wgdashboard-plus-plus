# Network Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live SSE-powered WireGuard diagnostic terminal — unified view in Settings and per-interface view replacing the current collapsible panel content.

**Architecture:** New Python module `WireguardDiagnostics.py` collects data from `wg show`, `ip route`, `ip address`, cross-references AllowedIPs with system routes, and streams changes via SSE. Single shared Vue component `NetworkDiagnostics.vue` renders neon-styled terminal in both Settings tab and interface panel. Background monitor thread runs every 1s, pushes only on change.

**Tech Stack:** Python/Flask (SSE generator), Vue 3 (EventSource API), existing subprocess/threading patterns.

**Deployment:** Staging (192.168.100.161:10086) first → verify → push to GitLab → deploy to Prod (116.203.226.32).

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/modules/WireguardDiagnostics.py` | Collect WG + route data, detect warnings, compare state |
| Create | `src/static/app/src/components/networkDiagnostics/NetworkDiagnostics.vue` | Shared neon terminal component (mode=all/single) |
| Create | `src/static/app/src/components/settingsComponent/networkDiagnosticsSettings.vue` | Settings tab wrapper |
| Create | `src/tests/test_diagnostics.py` | Backend tests for diagnostics module |
| Modify | `src/dashboard.py` | Add SSE endpoint, start monitor thread |
| Modify | `src/gunicorn.conf.py` | Increase threads 2→4 |
| Modify | `src/static/app/src/router/router.js` | Add settings child route |
| Modify | `src/static/app/src/views/settings.vue` | Add tab to tabs array |
| Modify | `src/static/app/src/components/configurationComponents/peerList.vue` | Replace collapsible panel content |

---

### Task 1: WireguardDiagnostics module — data collection

**Files:**
- Create: `src/modules/WireguardDiagnostics.py`
- Create: `src/tests/test_diagnostics.py`

- [ ] **Step 1: Write failing test for collecting interface info**

```python
# src/tests/test_diagnostics.py
import pytest
from unittest.mock import patch, MagicMock
import json

class TestDiagnosticsCollector:
    """Tests for WireguardDiagnostics data collection."""

    def test_collect_interface_info_up(self):
        """Collect interface state, mtu, fwmark from ip address show."""
        from modules.WireguardDiagnostics import DiagnosticsCollector

        ip_addr_output = (
            "4: wg0: <POINTOPOINT,NOARP,UP,LOWER_UP> mtu 1420 qdisc noqueue state UNKNOWN group default qlen 1000\n"
            "    link/none\n"
            "    inet 10.200.0.1/24 scope global wg0\n"
            "       valid_lft forever preferred_lft forever\n"
        )

        with patch("subprocess.check_output", return_value=ip_addr_output.encode("utf-8")):
            collector = DiagnosticsCollector()
            result = collector.collect_interface_info("wg0")

        assert result["status"] == "up"
        assert result["mtu"] == 1420
        assert result["address"] == "10.200.0.1/24"

    def test_collect_interface_info_down(self):
        """Interface that is down should return status=down."""
        from modules.WireguardDiagnostics import DiagnosticsCollector

        ip_addr_output = (
            "4: wg0: <POINTOPOINT,NOARP> mtu 1420 qdisc noqueue state DOWN group default qlen 1000\n"
            "    link/none\n"
            "    inet 10.200.0.1/24 scope global wg0\n"
        )

        with patch("subprocess.check_output", return_value=ip_addr_output.encode("utf-8")):
            collector = DiagnosticsCollector()
            result = collector.collect_interface_info("wg0")

        assert result["status"] == "down"

    def test_collect_interface_info_not_exist(self):
        """Non-existent interface returns None."""
        import subprocess
        from modules.WireguardDiagnostics import DiagnosticsCollector

        with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "ip")):
            collector = DiagnosticsCollector()
            result = collector.collect_interface_info("wg99")

        assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_diagnostics.py::TestDiagnosticsCollector::test_collect_interface_info_up -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.WireguardDiagnostics'`

- [ ] **Step 3: Implement DiagnosticsCollector.collect_interface_info**

```python
# src/modules/WireguardDiagnostics.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_diagnostics.py::TestDiagnosticsCollector -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/modules/WireguardDiagnostics.py src/tests/test_diagnostics.py
git commit -m "feat(diagnostics): add DiagnosticsCollector with interface info collection"
```

---

### Task 2: Peer data collection

**Files:**
- Modify: `src/modules/WireguardDiagnostics.py`
- Modify: `src/tests/test_diagnostics.py`

- [ ] **Step 1: Write failing test for peer collection**

```python
# Add to src/tests/test_diagnostics.py TestDiagnosticsCollector class

    def test_collect_peers(self):
        """Collect peer data from wg show including handshake, transfer, endpoints, allowed-ips."""
        from modules.WireguardDiagnostics import DiagnosticsCollector

        wg_show_output = (
            "interface: wg0\n"
            "  public key: ServerPubKey=\n"
            "  private key: (hidden)\n"
            "  listening port: 65350\n"
            "  fwmark: 0xca6c\n"
            "\n"
            "peer: PeerPubKeyA=\n"
            "  endpoint: 85.10.42.1:51820\n"
            "  allowed ips: 10.200.0.2/32, 192.168.1.0/24\n"
            "  latest handshake: 12 seconds ago\n"
            "  transfer: 25.16 MiB received, 1.05 GiB sent\n"
            "\n"
            "peer: PeerPubKeyB=\n"
            "  allowed ips: 10.200.0.3/32\n"
            "  transfer: 0 B received, 0 B sent\n"
        )

        with patch("subprocess.check_output", return_value=wg_show_output.encode("utf-8")):
            collector = DiagnosticsCollector()
            iface_data, peers = collector.collect_peers("wg0")

        assert iface_data["publicKey"] == "ServerPubKey="
        assert iface_data["listenPort"] == 65350
        assert iface_data["fwmark"] == "0xca6c"
        assert len(peers) == 2
        assert peers[0]["publicKey"] == "PeerPubKeyA="
        assert peers[0]["endpoint"] == "85.10.42.1:51820"
        assert peers[0]["allowedIps"] == ["10.200.0.2/32", "192.168.1.0/24"]
        assert peers[0]["latestHandshake"] == "12 seconds ago"
        assert peers[0]["status"] == "online"
        assert peers[1]["publicKey"] == "PeerPubKeyB="
        assert peers[1]["endpoint"] is None
        assert peers[1]["status"] == "inactive"

    def test_collect_peers_interface_down(self):
        """When interface is down, return empty."""
        import subprocess
        from modules.WireguardDiagnostics import DiagnosticsCollector

        with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "wg")):
            collector = DiagnosticsCollector()
            iface_data, peers = collector.collect_peers("wg0")

        assert iface_data is None
        assert peers == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_diagnostics.py::TestDiagnosticsCollector::test_collect_peers -v`
Expected: FAIL — `AttributeError: 'DiagnosticsCollector' object has no attribute 'collect_peers'`

- [ ] **Step 3: Implement collect_peers**

Add to `src/modules/WireguardDiagnostics.py` DiagnosticsCollector class:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_diagnostics.py::TestDiagnosticsCollector -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/modules/WireguardDiagnostics.py src/tests/test_diagnostics.py
git commit -m "feat(diagnostics): add peer data collection from wg show"
```

---

### Task 3: Route collection and cross-referencing

**Files:**
- Modify: `src/modules/WireguardDiagnostics.py`
- Modify: `src/tests/test_diagnostics.py`

- [ ] **Step 1: Write failing test for route collection**

```python
# Add to src/tests/test_diagnostics.py TestDiagnosticsCollector class

    def test_collect_routes(self):
        """Collect system routes for a WG interface from ip route."""
        from modules.WireguardDiagnostics import DiagnosticsCollector

        ip_route_output = (
            "10.200.0.0/24 dev wg0 proto kernel scope link src 10.200.0.1\n"
            "192.168.1.0/24 via 10.200.0.2 dev wg0 metric 100\n"
            "172.16.0.0/16 via 10.200.0.3 dev wg0 metric 100\n"
        )

        with patch("subprocess.check_output", return_value=ip_route_output.encode("utf-8")):
            collector = DiagnosticsCollector()
            routes = collector.collect_routes("wg0")

        assert len(routes) == 3
        assert routes[0]["destination"] == "10.200.0.0/24"
        assert routes[0]["gateway"] == "kernel"
        assert routes[1]["destination"] == "192.168.1.0/24"
        assert routes[1]["gateway"] == "10.200.0.2"
        assert routes[1]["metric"] == 100
```

- [ ] **Step 2: Write failing test for cross-referencing routes with peers**

```python
    def test_cross_reference_routes_with_peers(self):
        """Match routes to peers via gateway IP in AllowedIPs, detect warnings."""
        from modules.WireguardDiagnostics import DiagnosticsCollector

        peers = [
            {
                "publicKey": "A=", "name": "office-gw",
                "endpoint": "85.10.42.1:51820",
                "allowedIps": ["10.200.0.2/32", "192.168.1.0/24"],
                "status": "online",
            },
            {
                "publicKey": "B=", "name": "backup-srv",
                "endpoint": None,
                "allowedIps": ["10.200.0.6/32", "10.0.99.0/24"],
                "status": "inactive",
            },
        ]
        routes = [
            {"destination": "10.200.0.0/24", "gateway": "kernel", "metric": 0},
            {"destination": "192.168.1.0/24", "gateway": "10.200.0.2", "metric": 100},
            {"destination": "10.0.99.0/24", "gateway": "10.200.0.6", "metric": 100},
        ]

        collector = DiagnosticsCollector()
        annotated, warnings = collector.cross_reference(routes, peers, "10.200.0.0/24")

        assert annotated[0]["statusText"] == "interface subnet"
        assert annotated[1]["peer"] == "office-gw"
        assert annotated[1]["statusText"] == "AllowedIPs match"
        assert annotated[2]["peer"] == "backup-srv"
        assert "peer inactive" in annotated[2]["statusText"]
        assert any("backup-srv" in w["message"] for w in warnings)

    def test_cross_reference_missing_route(self):
        """AllowedIPs entry without corresponding system route generates warning."""
        from modules.WireguardDiagnostics import DiagnosticsCollector

        peers = [
            {
                "publicKey": "A=", "name": "gw",
                "allowedIps": ["10.200.0.2/32", "192.168.5.0/24"],
                "status": "online",
            },
        ]
        routes = [
            {"destination": "10.200.0.0/24", "gateway": "kernel", "metric": 0},
        ]

        collector = DiagnosticsCollector()
        annotated, warnings = collector.cross_reference(routes, peers, "10.200.0.0/24")

        missing = [w for w in warnings if w["type"] == "missing_route"]
        assert len(missing) == 1
        assert "192.168.5.0/24" in missing[0]["message"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_diagnostics.py -k "route" -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 4: Implement collect_routes and cross_reference**

Add to `src/modules/WireguardDiagnostics.py` DiagnosticsCollector class:

```python
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
                # If AllowedIP is a /32, the IP itself could be a gateway
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
```

- [ ] **Step 5: Run all tests**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_diagnostics.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/modules/WireguardDiagnostics.py src/tests/test_diagnostics.py
git commit -m "feat(diagnostics): add route collection and peer cross-referencing with warnings"
```

---

### Task 4: Full diagnostics snapshot and peer name resolution

**Files:**
- Modify: `src/modules/WireguardDiagnostics.py`
- Modify: `src/tests/test_diagnostics.py`

- [ ] **Step 1: Write failing test for full snapshot**

```python
# Add to src/tests/test_diagnostics.py

class TestDiagnosticsSnapshot:
    """Tests for building a complete diagnostics snapshot."""

    def test_build_snapshot_single_interface(self):
        """Build complete snapshot for one interface, including peer name resolution."""
        from modules.WireguardDiagnostics import DiagnosticsCollector

        ip_addr_output = (
            "4: wg0: <POINTOPOINT,NOARP,UP,LOWER_UP> mtu 1420 qdisc noqueue state UNKNOWN\n"
            "    inet 10.200.0.1/24 scope global wg0\n"
        )
        wg_show_output = (
            "interface: wg0\n"
            "  public key: SrvKey=\n"
            "  listening port: 65350\n"
            "  fwmark: 0xca6c\n"
            "\n"
            "peer: PeerKeyA=\n"
            "  endpoint: 85.10.42.1:51820\n"
            "  allowed ips: 10.200.0.2/32, 192.168.1.0/24\n"
            "  latest handshake: 12 seconds ago\n"
            "  transfer: 25.16 MiB received, 1.05 GiB sent\n"
        )
        ip_route_output = (
            "10.200.0.0/24 dev wg0 proto kernel scope link src 10.200.0.1\n"
            "192.168.1.0/24 via 10.200.0.2 dev wg0 metric 100\n"
        )

        call_map = {
            "ip address show wg0": ip_addr_output.encode("utf-8"),
            "wg show wg0": wg_show_output.encode("utf-8"),
            "ip route show dev wg0": ip_route_output.encode("utf-8"),
        }

        def mock_check_output(cmd, **kwargs):
            for key, val in call_map.items():
                if key in cmd:
                    return val
            raise subprocess.CalledProcessError(1, cmd)

        peer_names = {"PeerKeyA=": "office-gw"}

        with patch("subprocess.check_output", side_effect=mock_check_output):
            collector = DiagnosticsCollector()
            snapshot = collector.build_snapshot("wg0", protocol="wg", peer_names=peer_names)

        assert snapshot["status"] == "up"
        assert snapshot["listenPort"] == 65350
        assert len(snapshot["peers"]) == 1
        assert snapshot["peers"][0]["name"] == "office-gw"
        assert snapshot["peers"][0]["status"] == "online"
        assert len(snapshot["routes"]) == 2
        assert snapshot["routes"][1]["peer"] == "office-gw"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_diagnostics.py::TestDiagnosticsSnapshot -v`
Expected: FAIL

- [ ] **Step 3: Implement build_snapshot**

Add to `src/modules/WireguardDiagnostics.py` DiagnosticsCollector class:

```python
    def build_snapshot(self, interface: str, protocol: str = "wg", peer_names: dict = None) -> dict | None:
        """Build complete diagnostics snapshot for one interface.

        Args:
            interface: WG interface name (e.g. "wg0")
            protocol: "wg" or "awg"
            peer_names: dict mapping public_key → friendly name
        """
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
```

- [ ] **Step 4: Run all diagnostics tests**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_diagnostics.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/modules/WireguardDiagnostics.py src/tests/test_diagnostics.py
git commit -m "feat(diagnostics): add full snapshot builder with peer name resolution"
```

---

### Task 5: SSE endpoint and monitor thread

**Files:**
- Modify: `src/modules/WireguardDiagnostics.py`
- Modify: `src/dashboard.py`
- Modify: `src/gunicorn.conf.py`

- [ ] **Step 1: Add DiagnosticsMonitor class to WireguardDiagnostics.py**

Add at the end of `src/modules/WireguardDiagnostics.py`:

```python
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
        """Start the background monitor thread.

        Args:
            get_configurations: callable returning dict of {name: WireguardConfiguration}
            app_logger: Flask app logger
        """
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

                # Check per-interface what changed
                with self._lock:
                    for name, snap in full_snapshot.items():
                        snap_json = json.dumps(snap, sort_keys=True)
                        if self._last_state.get(name) != snap_json:
                            self._last_state[name] = snap_json
                            # Notify relevant subscribers
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
```

- [ ] **Step 2: Add SSE endpoint to dashboard.py**

Find the imports section near the top of `src/dashboard.py` and add:

```python
from modules.WireguardDiagnostics import DiagnosticsMonitor
```

Add after the line `AllBackupScheduler = None` (or near other global initializations):

```python
AllDiagnosticsMonitor = DiagnosticsMonitor()
```

Add the SSE endpoint (near other API endpoints):

```python
@app.route(f'{APP_PREFIX}/api/sse/diagnostics', methods=['GET'])
def API_SSE_Diagnostics():
    if not current_user:
        return ResponseObject(False, "Invalid authentication.", status_code=401)

    interface = request.args.get('interface', None)
    interfaces_filter = [interface] if interface else None

    def generate():
        import queue as queue_module
        q = AllDiagnosticsMonitor.subscribe(interfaces_filter)
        try:
            # Send initial full state
            initial = {}
            for name in (interfaces_filter or WireguardConfigurations.keys()):
                if name in AllDiagnosticsMonitor._last_state:
                    initial[name] = json.loads(AllDiagnosticsMonitor._last_state[name])
            if initial:
                yield f"data: {json.dumps({'interfaces': initial, 'timestamp': int(time.time())})}\n\n"

            heartbeat_interval = 15
            last_heartbeat = time.time()

            while True:
                try:
                    payload = q.get(timeout=1)
                    yield f"data: {payload}\n\n"
                except queue_module.Empty:
                    if time.time() - last_heartbeat >= heartbeat_interval:
                        yield ": heartbeat\n\n"
                        last_heartbeat = time.time()
        finally:
            AllDiagnosticsMonitor.unsubscribe(q)

    return app.response_class(generate(), mimetype='text/event-stream',
                              headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
```

Add to `startThreads()` function (after BackupScheduler start):

```python
    AllDiagnosticsMonitor.start(lambda: WireguardConfigurations, app.logger)
```

- [ ] **Step 3: Increase gunicorn threads**

In `src/gunicorn.conf.py`, change:

```python
threads = 2
```

to:

```python
threads = 4
```

- [ ] **Step 4: Run existing tests to verify nothing is broken**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/ -v --timeout=30`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/modules/WireguardDiagnostics.py src/dashboard.py src/gunicorn.conf.py
git commit -m "feat(diagnostics): add SSE endpoint and DiagnosticsMonitor background thread"
```

---

### Task 6: NetworkDiagnostics.vue — shared terminal component

**Files:**
- Create: `src/static/app/src/components/networkDiagnostics/NetworkDiagnostics.vue`

- [ ] **Step 1: Create the component**

```vue
<!-- src/static/app/src/components/networkDiagnostics/NetworkDiagnostics.vue -->
<template>
  <div class="neon-terminal" :class="{ 'neon-terminal--single': mode === 'single' }">
    <template v-if="mode === 'single'">
      <div class="neon-info-bar">
        <div class="neon-info-item">
          <span class="neon-label">ADDRESS</span>
          <span class="neon-cyan">{{ interfaceData?.address || '—' }}</span>
        </div>
        <div class="neon-info-item">
          <span class="neon-label">PORT</span>
          <span class="neon-text">{{ interfaceData?.listenPort || '—' }}</span>
        </div>
        <div class="neon-info-item">
          <span class="neon-label">PEERS</span>
          <span class="neon-green">{{ onlinePeers }}</span>
          <span class="neon-muted"> / {{ totalPeers }}</span>
        </div>
        <div class="neon-info-item">
          <span class="neon-label">TRAFFIC</span>
          <span class="neon-cyan">↓ {{ formatBytes(totalRx) }}</span>&nbsp;&nbsp;
          <span class="neon-orange">↑ {{ formatBytes(totalTx) }}</span>
        </div>
        <div class="neon-info-item ms-auto">
          <span class="neon-label">PUBLIC KEY</span>
          <span class="neon-muted neon-small" role="button" @click="copyKey">
            {{ truncateKey(interfaceData?.publicKey) }} <span class="neon-purple">⧉</span>
          </span>
        </div>
      </div>
    </template>

    <template v-for="(iface, ifaceName) in allInterfaces" :key="ifaceName">
      <div class="neon-body">
        <div v-if="mode === 'all'" class="neon-section-header neon-purple">
          ── {{ ifaceName }} ──
        </div>

        <!-- Interface -->
        <div class="neon-section">
          <div class="neon-section-header neon-purple">── Interface ──</div>
          <div class="neon-row-inline">
            <span class="neon-muted">state:</span>
            <span :class="iface.status === 'up' ? 'neon-green pulse-green' : 'neon-red pulse-red'">●</span>
            <span :class="iface.status === 'up' ? 'neon-green' : 'neon-red'">{{ iface.status?.toUpperCase() }}</span>
            &nbsp;&nbsp;&nbsp;
            <span class="neon-muted">mtu:</span>
            <span class="neon-text">{{ iface.mtu || '—' }}</span>
            &nbsp;&nbsp;&nbsp;
            <template v-if="iface.fwmark">
              <span class="neon-muted">fwmark:</span>
              <span class="neon-text">{{ iface.fwmark }}</span>
            </template>
          </div>
        </div>

        <!-- Peers -->
        <div class="neon-section" v-if="iface.peers?.length">
          <div class="neon-section-header neon-purple">── Peers ──</div>
          <table class="neon-table">
            <thead>
              <tr class="neon-muted">
                <td>PEER</td><td>ENDPOINT</td><td>ALLOWED IPS</td>
                <td>HANDSHAKE</td><td>TRANSFER</td><td>STATUS</td>
              </tr>
            </thead>
            <tbody>
              <tr v-for="peer in iface.peers" :key="peer.publicKey" class="neon-table-row">
                <td class="neon-text">{{ peer.name }}</td>
                <td :class="peer.endpoint ? 'neon-text' : 'neon-muted'">{{ peer.endpoint || '(none)' }}</td>
                <td class="neon-text">{{ peer.allowedIps?.join(', ') }}</td>
                <td :class="handshakeClass(peer)">{{ peer.latestHandshake || 'never' }}</td>
                <td>
                  <template v-if="peer.transferRx || peer.transferTx">
                    <span class="neon-cyan">↓{{ formatBytes(peer.transferRx) }}</span>
                    <span class="neon-orange"> ↑{{ formatBytes(peer.transferTx) }}</span>
                  </template>
                  <span v-else class="neon-muted">—</span>
                </td>
                <td>
                  <span :class="statusIndicatorClass(peer.status)">●</span>
                  <span :class="statusTextClass(peer.status)">{{ peer.status }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Routes -->
        <div class="neon-section" v-if="iface.routes?.length">
          <div class="neon-section-header neon-purple">
            ── System Routes{{ mode === 'single' ? ` (via ${ifaceName})` : ` (via ${ifaceName})` }} ──
          </div>
          <table class="neon-table">
            <thead>
              <tr class="neon-muted">
                <td>DESTINATION</td><td>GATEWAY</td><td>METRIC</td><td>PEER</td><td>STATUS</td>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(route, idx) in iface.routes" :key="idx" class="neon-table-row">
                <td class="neon-cyan">{{ route.destination }}</td>
                <td class="neon-text">{{ route.gateway }}</td>
                <td class="neon-text">{{ route.metric }}</td>
                <td :class="route.peer ? 'neon-text' : 'neon-muted'">{{ route.peer || '—' }}</td>
                <td>
                  <template v-if="route.status === 'ok'">
                    <span class="neon-green">✓ {{ route.statusText }}</span>
                  </template>
                  <template v-else>
                    <span class="neon-orange pulse-orange">⚠</span>
                    <span class="neon-orange"> {{ route.statusText }}</span>
                  </template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Warnings -->
        <div class="neon-section" v-if="iface.warnings?.length">
          <div class="neon-section-header neon-red">── Warnings ──</div>
          <div v-for="(w, idx) in iface.warnings" :key="idx" class="neon-warning-row">
            <span class="neon-orange pulse-orange">⚠</span>
            <span class="neon-text">{{ w.target }}</span>
            <span class="neon-muted"> — {{ w.message }}</span>
          </div>
        </div>
      </div>
    </template>

    <!-- Footer -->
    <div class="neon-footer">
      <span class="neon-muted">
        <span :class="connected ? 'neon-green pulse-green' : 'neon-red pulse-red'">●</span>
        {{ connected ? 'SSE connected — live updates' : 'SSE disconnected — reconnecting...' }}
      </span>
      <span class="neon-muted">Last event: {{ lastEventTime }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { getUrl } from '@/utilities/fetch.js';

const props = defineProps({
  mode: { type: String, default: 'all' },       // 'all' or 'single'
  interface: { type: String, default: null },    // required when mode='single'
});

const interfaces = ref({});
const connected = ref(false);
const lastEventTime = ref('—');
let eventSource = null;

const allInterfaces = computed(() => interfaces.value);

const interfaceData = computed(() => {
  if (props.mode === 'single' && props.interface) {
    return interfaces.value[props.interface] || null;
  }
  return null;
});

const onlinePeers = computed(() => {
  const iface = interfaceData.value;
  if (!iface?.peers) return 0;
  return iface.peers.filter(p => p.status === 'online').length;
});

const totalPeers = computed(() => {
  const iface = interfaceData.value;
  return iface?.peers?.length || 0;
});

const totalRx = computed(() => {
  const iface = interfaceData.value;
  if (!iface?.peers) return 0;
  return iface.peers.reduce((sum, p) => sum + (p.transferRx || 0), 0);
});

const totalTx = computed(() => {
  const iface = interfaceData.value;
  if (!iface?.peers) return 0;
  return iface.peers.reduce((sum, p) => sum + (p.transferTx || 0), 0);
});

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const units = ['B', 'K', 'M', 'G', 'T'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const val = (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0);
  return `${val}${units[i]}`;
}

function truncateKey(key) {
  if (!key) return '—';
  return key.slice(0, 8) + '…' + key.slice(-4);
}

function copyKey() {
  const key = interfaceData.value?.publicKey;
  if (key) navigator.clipboard.writeText(key);
}

function handshakeClass(peer) {
  if (peer.status === 'online') return 'neon-green';
  if (peer.status === 'offline') return 'neon-red';
  return 'neon-muted';
}

function statusIndicatorClass(status) {
  if (status === 'online') return 'neon-green pulse-green';
  if (status === 'offline') return 'neon-red pulse-red';
  return 'neon-muted';
}

function statusTextClass(status) {
  if (status === 'online') return 'neon-green';
  if (status === 'offline') return 'neon-red';
  return 'neon-muted';
}

function connectSSE() {
  const params = props.mode === 'single' && props.interface
    ? `?interface=${props.interface}`
    : '';
  const url = getUrl(`/api/sse/diagnostics${params}`);

  eventSource = new EventSource(url);

  eventSource.onopen = () => {
    connected.value = true;
  };

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.interfaces) {
      for (const [name, snap] of Object.entries(data.interfaces)) {
        interfaces.value[name] = snap;
      }
    }
    const now = new Date();
    lastEventTime.value = now.toLocaleTimeString();
  };

  eventSource.onerror = () => {
    connected.value = false;
    // EventSource auto-reconnects
  };
}

onMounted(() => {
  connectSSE();
});

onBeforeUnmount(() => {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
});
</script>

<style scoped>
@keyframes pulse-green-anim {
  0%, 100% { opacity: 1; text-shadow: 0 0 4px #50fa7b, 0 0 8px rgba(80,250,123,0.27); }
  50% { opacity: 0.6; text-shadow: 0 0 2px rgba(80,250,123,0.4); }
}
@keyframes pulse-red-anim {
  0%, 100% { opacity: 1; text-shadow: 0 0 4px #ff5555, 0 0 8px rgba(255,85,85,0.27); }
  50% { opacity: 0.6; text-shadow: 0 0 2px rgba(255,85,85,0.4); }
}
@keyframes pulse-orange-anim {
  0%, 100% { opacity: 1; text-shadow: 0 0 4px #ffb86c, 0 0 8px rgba(255,184,108,0.27); }
  50% { opacity: 0.6; text-shadow: 0 0 2px rgba(255,184,108,0.4); }
}

.neon-terminal {
  background: rgba(30, 30, 35, 0.85);
  backdrop-filter: blur(8px);
  border-radius: 8px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 13px;
  overflow: hidden;
}

.neon-info-bar {
  display: flex;
  gap: 24px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.03);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  align-items: center;
  flex-wrap: wrap;
}

.neon-info-item { display: flex; flex-direction: column; }
.neon-label { color: #6b7394; font-size: 11px; text-shadow: 0 0 1px rgba(107,115,148,0.07); }
.neon-small { font-size: 11px; }

.neon-body { padding: 16px; line-height: 1.8; }

.neon-section { padding-bottom: 12px; margin-top: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }
.neon-section:last-of-type { border-bottom: none; }
.neon-section-header { font-weight: bold; margin-bottom: 6px; }
.neon-row-inline { padding-left: 8px; }

.neon-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.neon-table td { padding: 4px 12px; }
.neon-table thead td { padding: 4px 12px 6px; }
.neon-table-row:hover { background: rgba(255, 255, 255, 0.03); }

.neon-warning-row { padding-left: 8px; line-height: 2; }

.neon-footer {
  margin: 0 16px;
  padding: 10px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  justify-content: space-between;
  font-size: 11px;
}

/* Neon colors */
.neon-green { color: #50fa7b; text-shadow: 0 0 4px rgba(80,250,123,0.4), 0 0 10px rgba(80,250,123,0.13); }
.neon-red { color: #ff5555; text-shadow: 0 0 4px rgba(255,85,85,0.4), 0 0 10px rgba(255,85,85,0.13); }
.neon-cyan { color: #8be9fd; text-shadow: 0 0 4px rgba(139,233,253,0.27), 0 0 8px rgba(139,233,253,0.13); }
.neon-orange { color: #ffb86c; text-shadow: 0 0 4px rgba(255,184,108,0.27), 0 0 8px rgba(255,184,108,0.13); }
.neon-purple { color: #bd93f9; text-shadow: 0 0 4px rgba(189,147,249,0.4), 0 0 10px rgba(189,147,249,0.13); }
.neon-text { color: #e2e8f0; text-shadow: 0 0 2px rgba(226,232,240,0.13); }
.neon-muted { color: #6b7394; text-shadow: 0 0 1px rgba(107,115,148,0.07); }

/* Pulse animations */
.pulse-green { animation: pulse-green-anim 2s ease-in-out infinite; }
.pulse-red { animation: pulse-red-anim 1.5s ease-in-out infinite; }
.pulse-orange { animation: pulse-orange-anim 1.8s ease-in-out infinite; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add src/static/app/src/components/networkDiagnostics/NetworkDiagnostics.vue
git commit -m "feat(diagnostics): add NetworkDiagnostics.vue neon terminal component"
```

---

### Task 7: Settings tab integration

**Files:**
- Create: `src/static/app/src/components/settingsComponent/networkDiagnosticsSettings.vue`
- Modify: `src/static/app/src/router/router.js`
- Modify: `src/static/app/src/views/settings.vue`

- [ ] **Step 1: Create settings wrapper component**

```vue
<!-- src/static/app/src/components/settingsComponent/networkDiagnosticsSettings.vue -->
<template>
  <div>
    <NetworkDiagnostics mode="all" />
  </div>
</template>

<script setup>
import NetworkDiagnostics from "@/components/networkDiagnostics/NetworkDiagnostics.vue";
</script>
```

- [ ] **Step 2: Add route to router.js**

In `src/static/app/src/router/router.js`, add a new child inside the Settings children array, after the Backup & Restore entry (after line ~76):

```javascript
                    {
                        name: "Network Diagnostics",
                        path: "network_diagnostics",
                        component: () => import("@/components/settingsComponent/networkDiagnosticsSettings.vue"),
                        meta: {
                            title: "Network Diagnostics"
                        }
                    }
```

- [ ] **Step 3: Add tab to settings.vue**

In `src/static/app/src/views/settings.vue`, add to the `tabs` array after the Backup & Restore entry:

```javascript
                    {
                        id: "network_diagnostics",
                        title: "Network Diagnostics"
                    }
```

- [ ] **Step 4: Commit**

```bash
git add src/static/app/src/components/settingsComponent/networkDiagnosticsSettings.vue \
        src/static/app/src/router/router.js \
        src/static/app/src/views/settings.vue
git commit -m "feat(diagnostics): add Network Diagnostics tab in Settings"
```

---

### Task 8: Collapsible panel redesign

**Files:**
- Modify: `src/static/app/src/components/configurationComponents/peerList.vue`

- [ ] **Step 1: Add NetworkDiagnostics import**

In `src/static/app/src/components/configurationComponents/peerList.vue`, add to the `<script setup>` imports section:

```javascript
import NetworkDiagnostics from "@/components/networkDiagnostics/NetworkDiagnostics.vue";
```

- [ ] **Step 2: Replace collapsible panel content**

In `peerList.vue`, replace the entire `<Transition name="fade2">` block (lines 432-520 — the block that starts with `<Transition name="fade2">` and contains Address/Port/Key cards, stat cards, and PeerDataUsageCharts) with:

```vue
		<Transition name="fade2">
			<div v-if="configInfoExpanded" class="border-top">
				<NetworkDiagnostics mode="single" :interface="configurationInfo.Name" />
			</div>
		</Transition>
```

- [ ] **Step 3: Remove unused PeerDataUsageCharts import (if exists)**

If `PeerDataUsageCharts` is imported in the script section and no longer used elsewhere in the template, remove the import line. Also remove `ConfigurationDescription` import if only used in the removed block.

- [ ] **Step 4: Build frontend to verify no errors**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src/static/app && npm run build`
Expected: Build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add src/static/app/src/components/configurationComponents/peerList.vue
git commit -m "feat(diagnostics): replace collapsible panel with neon diagnostic terminal"
```

---

### Task 9: SSE authentication for EventSource

**Files:**
- Modify: `src/static/app/src/components/networkDiagnostics/NetworkDiagnostics.vue`

EventSource doesn't support custom headers. Flask session cookies are sent automatically for same-origin requests, which works. But for cross-server mode (API key auth), we need a workaround.

- [ ] **Step 1: Update connectSSE to handle cross-server mode**

In `NetworkDiagnostics.vue`, update the `connectSSE` function. Replace the existing function with:

```javascript
function connectSSE() {
  const params = new URLSearchParams();
  if (props.mode === 'single' && props.interface) {
    params.set('interface', props.interface);
  }

  // For cross-server mode, pass API key as query param since EventSource
  // doesn't support custom headers
  const store = (await import('@/stores/DashboardConfigurationStore.js')).DashboardConfigurationStore();
  const crossServer = store.getActiveCrossServer();
  if (crossServer) {
    params.set('apikey', crossServer.apiKey);
  }

  const paramStr = params.toString();
  const url = getUrl(`/api/sse/diagnostics${paramStr ? '?' + paramStr : ''}`);

  eventSource = new EventSource(url);
  // ... rest stays the same
```

Also update the SSE endpoint in `dashboard.py` to accept `apikey` query param:

In `API_SSE_Diagnostics()`, before the authentication check, add:

```python
    # Support API key via query param for EventSource (which can't set headers)
    apikey = request.args.get('apikey', None)
    if apikey:
        # Validate API key same as other endpoints
        from modules.DashboardConfig import DashboardConfig
        if not DashboardConfig.ValidateAPIKey(apikey):
            return ResponseObject(False, "Invalid API key.", status_code=401)
    elif not current_user:
        return ResponseObject(False, "Invalid authentication.", status_code=401)
```

- [ ] **Step 2: Commit**

```bash
git add src/static/app/src/components/networkDiagnostics/NetworkDiagnostics.vue src/dashboard.py
git commit -m "feat(diagnostics): add API key auth support for SSE EventSource"
```

---

### Task 10: Deploy to staging and verify

**Files:** No code changes — deployment and verification.

- [ ] **Step 1: Build frontend**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src/static/app && npm run build`
Expected: Build succeeds.

- [ ] **Step 2: Run all tests**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 3: Deploy to staging (192.168.100.161:10086)**

Deploy the updated code to staging server. Restart WGDashboard service.

- [ ] **Step 4: Verify on staging**

Check manually:
1. Settings → "Network Diagnostics" tab appears and shows all WG interfaces
2. Open a WG interface → collapsible panel shows neon diagnostic terminal
3. SSE connects (green pulsing dot in footer)
4. Data updates live when peer connects/disconnects
5. Warnings appear for offline peers and route mismatches
6. No console errors in browser

- [ ] **Step 5: Push to GitLab and deploy to production**

Only after staging verification passes:
```bash
git push gitlab main
```
Deploy to production (116.203.226.32).

- [ ] **Step 6: Verify on production**

Same checks as staging step 4.
