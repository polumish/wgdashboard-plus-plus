import pytest
import subprocess
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


class TestInterfaceCounters:
    """Tests for the /sys/class/net/<iface>/statistics/ counter integration
    added for v1.7.0 Network Diagnostics."""

    def test_counters_populated_from_sysfs(self, tmp_path, monkeypatch):
        """collect_interface_info should read rx/tx/errors/dropped from sysfs."""
        from modules.WireguardDiagnostics import DiagnosticsCollector

        # Stub _read_iface_counter to return deterministic values per name
        stub_values = {
            "rx_packets": 1234,
            "tx_packets": 5678,
            "rx_errors": 0,
            "tx_errors": 2,
            "rx_dropped": 7,
            "tx_dropped": 0,
        }
        monkeypatch.setattr(
            DiagnosticsCollector, "_read_iface_counter",
            staticmethod(lambda iface, name: stub_values.get(name, 0))
        )

        ip_addr_output = (
            "4: wg0: <POINTOPOINT,NOARP,UP,LOWER_UP> mtu 1420 qdisc noqueue state UNKNOWN\n"
            "    inet 10.200.0.1/24 scope global wg0\n"
        )

        with patch("subprocess.check_output", return_value=ip_addr_output.encode("utf-8")):
            collector = DiagnosticsCollector()
            result = collector.collect_interface_info("wg0")

        assert "counters" in result
        assert result["counters"]["rx_packets"] == 1234
        assert result["counters"]["tx_packets"] == 5678
        assert result["counters"]["tx_errors"] == 2
        assert result["counters"]["rx_dropped"] == 7

    def test_read_iface_counter_missing_file(self, tmp_path, monkeypatch):
        """_read_iface_counter returns 0 if the sysfs file is missing."""
        from modules.WireguardDiagnostics import DiagnosticsCollector
        # Point at a definitely-missing interface
        result = DiagnosticsCollector._read_iface_counter("nonexistent-iface-xyz", "rx_packets")
        assert result == 0


class TestPmtuStateLoader:
    """Tests for load_pmtu_state() reading /var/lib/wg-pmtu/state.json."""

    def test_load_valid_state(self, tmp_path, monkeypatch):
        from modules import WireguardDiagnostics
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "generated_at": "2026-04-10T10:00:00Z",
            "peers": {
                "PeerPubKey=": {
                    "iface": "wg0",
                    "pmtu": 1400,
                    "source": "tracepath",
                }
            }
        }))
        monkeypatch.setattr(WireguardDiagnostics, "PMTU_STATE_FILE", str(state_file))

        peers = WireguardDiagnostics.load_pmtu_state()
        assert "PeerPubKey=" in peers
        assert peers["PeerPubKey="]["pmtu"] == 1400
        assert peers["PeerPubKey="]["source"] == "tracepath"

    def test_load_missing_file(self, tmp_path, monkeypatch):
        """Missing state file returns empty dict (PMTU is optional aux data)."""
        from modules import WireguardDiagnostics
        monkeypatch.setattr(
            WireguardDiagnostics, "PMTU_STATE_FILE", str(tmp_path / "does-not-exist.json")
        )
        assert WireguardDiagnostics.load_pmtu_state() == {}

    def test_load_invalid_json(self, tmp_path, monkeypatch):
        """Corrupted JSON should not crash — just return empty dict."""
        from modules import WireguardDiagnostics
        bad = tmp_path / "state.json"
        bad.write_text("{ this is not valid json")
        monkeypatch.setattr(WireguardDiagnostics, "PMTU_STATE_FILE", str(bad))
        assert WireguardDiagnostics.load_pmtu_state() == {}


class TestPmtuSnapshotIntegration:
    """Tests that build_snapshot attaches PMTU data and generates warnings
    when detected path MTU is below interface MTU + WG overhead (80)."""

    def _build_with_pmtu(self, monkeypatch, pmtu_state):
        from modules.WireguardDiagnostics import DiagnosticsCollector
        from modules import WireguardDiagnostics

        monkeypatch.setattr(WireguardDiagnostics, "load_pmtu_state", lambda: pmtu_state)

        ip_addr_output = (
            "4: wg0: <POINTOPOINT,NOARP,UP,LOWER_UP> mtu 1320 qdisc noqueue state UNKNOWN\n"
            "    inet 10.200.0.1/24 scope global wg0\n"
        )
        wg_show_output = (
            "interface: wg0\n"
            "  public key: SrvKey=\n"
            "  listening port: 51820\n"
            "\n"
            "peer: PeerGood=\n"
            "  endpoint: 1.2.3.4:51820\n"
            "  allowed ips: 10.200.0.2/32\n"
            "  latest handshake: 10 seconds ago\n"
            "  transfer: 1 MiB received, 1 MiB sent\n"
            "peer: PeerBad=\n"
            "  endpoint: 5.6.7.8:51820\n"
            "  allowed ips: 10.200.0.3/32\n"
            "  latest handshake: 10 seconds ago\n"
            "  transfer: 1 MiB received, 1 MiB sent\n"
        )
        ip_route_output = "10.200.0.0/24 dev wg0 proto kernel scope link src 10.200.0.1\n"

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

        with patch("subprocess.check_output", side_effect=mock_check_output):
            collector = DiagnosticsCollector()
            return collector.build_snapshot("wg0", protocol="wg")

    def test_pmtu_attached_to_peers(self, monkeypatch):
        """Each peer should get its PMTU data from load_pmtu_state()."""
        snapshot = self._build_with_pmtu(monkeypatch, {
            "PeerGood=": {"pmtu": 1500, "source": "tracepath"},
            "PeerBad=": {"pmtu": 1300, "source": "kernel"},
        })
        peers_by_key = {p["publicKey"]: p for p in snapshot["peers"]}
        assert peers_by_key["PeerGood="]["pmtu"] == 1500
        assert peers_by_key["PeerGood="]["pmtuSource"] == "tracepath"
        assert peers_by_key["PeerBad="]["pmtu"] == 1300
        assert peers_by_key["PeerBad="]["pmtuSource"] == "kernel"

    def test_pmtu_warning_generated_for_low_path_mtu(self, monkeypatch):
        """Peer with detected PMTU < interface_mtu + 80 should get a warning."""
        # Interface MTU is 1320, so required = 1400. 1300 < 1400 → warning.
        snapshot = self._build_with_pmtu(monkeypatch, {
            "PeerGood=": {"pmtu": 1500, "source": "tracepath"},  # OK
            "PeerBad=": {"pmtu": 1300, "source": "kernel"},      # too low
        })
        pmtu_warnings = [w for w in snapshot["warnings"] if w.get("type") == "pmtu_below_required"]
        assert len(pmtu_warnings) == 1
        assert "1300" in pmtu_warnings[0]["message"]
        assert "1400" in pmtu_warnings[0]["message"]  # required

    def test_no_pmtu_warning_when_unknown(self, monkeypatch):
        """Peers without detected PMTU should not produce warnings."""
        snapshot = self._build_with_pmtu(monkeypatch, {
            "PeerGood=": {"pmtu": None, "source": "unknown"},
            "PeerBad=": {"pmtu": None, "source": "unknown"},
        })
        pmtu_warnings = [w for w in snapshot["warnings"] if w.get("type") == "pmtu_below_required"]
        assert len(pmtu_warnings) == 0


class TestDashboardPmtuHelpers:
    """Tests for dashboard.py PMTU helper functions (_parse_target_ip,
    _atomic_write_pmtu_state)."""

    def test_parse_target_ip_valid_ipv4(self):
        from dashboard import _parse_target_ip
        assert _parse_target_ip("1.2.3.4") == "1.2.3.4"
        assert _parse_target_ip("  10.0.0.1  ") == "10.0.0.1"

    def test_parse_target_ip_valid_ipv6(self):
        from dashboard import _parse_target_ip
        assert _parse_target_ip("2001:db8::1") == "2001:db8::1"
        assert _parse_target_ip("[2001:db8::1]") == "2001:db8::1"

    def test_parse_target_ip_ipv6_zone_id_stripped(self):
        from dashboard import _parse_target_ip
        # Zone ID should be stripped before validation
        assert _parse_target_ip("fe80::1%eth0") == "fe80::1"

    def test_parse_target_ip_rejects_hostname(self):
        from dashboard import _parse_target_ip
        assert _parse_target_ip("example.com") is None
        assert _parse_target_ip("localhost") is None

    def test_parse_target_ip_rejects_garbage(self):
        from dashboard import _parse_target_ip
        assert _parse_target_ip("") is None
        assert _parse_target_ip(None) is None
        assert _parse_target_ip("not.an.ip.address.xxx") is None
        assert _parse_target_ip("1.2.3.4; rm -rf /") is None

    def test_atomic_write_pmtu_state(self, tmp_path, monkeypatch):
        """_atomic_write_pmtu_state reads, mutates, and atomically rewrites."""
        import dashboard
        monkeypatch.setattr(dashboard, "PMTU_STATE_DIR", str(tmp_path))
        monkeypatch.setattr(dashboard, "PMTU_STATE_FILE", str(tmp_path / "state.json"))
        monkeypatch.setattr(dashboard, "PMTU_LOCK_FILE", str(tmp_path / "state.lock"))

        # Initial write — no existing state
        def add_peer(state):
            state.setdefault("peers", {})["PeerA="] = {"pmtu": 1400}
        dashboard._atomic_write_pmtu_state(add_peer)

        state = json.loads((tmp_path / "state.json").read_text())
        assert "PeerA=" in state["peers"]
        assert state["peers"]["PeerA="]["pmtu"] == 1400

        # Second write — merges with existing
        def add_another(state):
            state["peers"]["PeerB="] = {"pmtu": 1320}
        dashboard._atomic_write_pmtu_state(add_another)

        state = json.loads((tmp_path / "state.json").read_text())
        assert "PeerA=" in state["peers"]
        assert "PeerB=" in state["peers"]

    def test_atomic_write_handles_corrupt_existing(self, tmp_path, monkeypatch):
        """If state.json exists but is corrupt, mutate_fn still runs on empty state."""
        import dashboard
        monkeypatch.setattr(dashboard, "PMTU_STATE_DIR", str(tmp_path))
        monkeypatch.setattr(dashboard, "PMTU_STATE_FILE", str(tmp_path / "state.json"))
        monkeypatch.setattr(dashboard, "PMTU_LOCK_FILE", str(tmp_path / "state.lock"))

        (tmp_path / "state.json").write_text("{ not valid json")

        def add_peer(state):
            state.setdefault("peers", {})["PeerA="] = {"pmtu": 1400}
        dashboard._atomic_write_pmtu_state(add_peer)

        state = json.loads((tmp_path / "state.json").read_text())
        assert "PeerA=" in state["peers"]
