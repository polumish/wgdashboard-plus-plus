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
