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
