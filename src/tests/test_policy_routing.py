"""Tests for PolicyRoutingManager."""
import sys
import os
import threading
from unittest.mock import patch, MagicMock, call
from dataclasses import asdict

import pytest

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _import_manager():
    from modules.PolicyRoutingManager import PolicyRoutingManager, PolicyRule
    return PolicyRoutingManager, PolicyRule


class TestPolicyRule:

    def test_policy_rule_fields(self):
        _, PolicyRule = _import_manager()
        rule = PolicyRule(
            config_name="wg-office",
            table_id=142,
            source_subnet="10.200.0.0/24",
            dest_subnet="10.0.50.0/24",
            device="wg-office",
            active=True,
        )
        assert rule.config_name == "wg-office"
        assert rule.table_id == 142
        assert rule.active is True

    def test_policy_rule_as_dict(self):
        _, PolicyRule = _import_manager()
        rule = PolicyRule(
            config_name="wg0",
            table_id=100,
            source_subnet="10.0.0.0/24",
            dest_subnet="10.0.50.0/24",
            device="wg0",
            active=False,
        )
        d = asdict(rule)
        assert d["config_name"] == "wg0"
        assert d["active"] is False


class TestTableId:

    def test_deterministic(self):
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        t1 = mgr._table_id("wg-office")
        t2 = mgr._table_id("wg-office")
        assert t1 == t2

    def test_range(self):
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        for name in ["wg0", "wg1", "wg-office", "nm-halfnet", "full-halfnet"]:
            tid = mgr._table_id(name)
            assert 100 <= tid <= 252, f"{name} got table_id {tid}"

    def test_different_configs_different_ids(self):
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        ids = {mgr._table_id(n) for n in ["wg0", "wg1", "wg-office"]}
        assert len(ids) == 3, "Expected different table IDs for different configs"

    def test_collision_resolution(self):
        """Two configs that hash to same value should get different table IDs."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        # Full-Halfnet and nm-halfnet both hash to 179
        t1 = mgr._table_id("Full-Halfnet")
        t2 = mgr._table_id("nm-halfnet")
        assert t1 != t2, f"Collision not resolved: both got {t1}"
        assert 100 <= t1 <= 252
        assert 100 <= t2 <= 252

    def test_collision_resolution_cached(self):
        """After collision resolution, repeated calls return same ID."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        t1 = mgr._table_id("Full-Halfnet")
        t2 = mgr._table_id("nm-halfnet")
        assert mgr._table_id("Full-Halfnet") == t1
        assert mgr._table_id("nm-halfnet") == t2


class TestConfigSubnet:

    def test_extracts_ipv4_network(self):
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        wc = MagicMock()
        wc.Address = "10.200.0.1/24"
        assert mgr.config_subnet(wc) == "10.200.0.0/24"

    def test_skips_ipv6(self):
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        wc = MagicMock()
        wc.Address = "fd00::1/64, 10.128.69.1/24"
        assert mgr.config_subnet(wc) == "10.128.69.0/24"

    def test_returns_none_for_empty(self):
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        wc = MagicMock()
        wc.Address = ""
        assert mgr.config_subnet(wc) is None


class TestApplyRules:

    def _make_wc(self, name, address, peers=None):
        """Create a mock WireguardConfiguration."""
        wc = MagicMock()
        wc.Name = name
        wc.Address = address
        wc.Peers = peers or []
        return wc

    def _make_gateway_peer(self, allowed_ip):
        """Create a mock gateway peer."""
        peer = MagicMock()
        peer.is_gateway = 1
        peer.allowed_ip = allowed_ip
        return peer

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_apply_creates_rules_for_gateway(self, mock_subprocess):
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()

        gateway = self._make_gateway_peer("10.0.50.0/24")
        wc = self._make_wc("wg-office", "10.200.0.1/24", peers=[gateway])
        mgr.init(lambda: {"wg-office": wc})

        # First call returns 0 (success deleting old rule), second returns 2 (no more rules)
        side_effects = []
        def run_side_effect(cmd, **kwargs):
            r = MagicMock()
            if cmd[:3] == ["ip", "rule", "del"]:
                if len(side_effects) == 0:
                    side_effects.append(1)
                    r.returncode = 2
                    r.stderr = "not found"
                else:
                    r.returncode = 2
                    r.stderr = "not found"
            else:
                r.returncode = 0
                r.stdout = "UP"
                r.stderr = ""
            return r
        mock_subprocess.run.side_effect = run_side_effect

        mgr.apply_rules("wg-office")

        status = mgr.get_status_for_config("wg-office")
        assert len(status) == 1
        assert status[0]["dest_subnet"] == "10.0.50.0/24"
        assert status[0]["source_subnet"] == "10.200.0.0/24"
        assert status[0]["active"] is True

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_apply_skips_own_subnet(self, mock_subprocess):
        """Gateway peer's WG IP within config subnet should be skipped."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()

        # Peer has both WG IP (in config subnet) and LAN behind it
        gateway = self._make_gateway_peer("10.200.0.5/32, 10.0.50.0/24")
        wc = self._make_wc("wg0", "10.200.0.1/24", peers=[gateway])
        mgr.init(lambda: {"wg0": wc})

        def run_se(cmd, **kwargs):
            r = MagicMock(returncode=0, stdout="UP", stderr="")
            if cmd[:3] == ["ip", "rule", "del"]:
                r.returncode = 2
                r.stderr = "not found"
            return r
        mock_subprocess.run.side_effect = run_se

        mgr.apply_rules("wg0")

        status = mgr.get_status_for_config("wg0")
        dest_subnets = [r["dest_subnet"] for r in status]
        assert "10.0.50.0/24" in dest_subnets
        # 10.200.0.5/32 is within 10.200.0.0/24 — should be excluded
        assert "10.200.0.5/32" not in dest_subnets

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_apply_interface_down(self, mock_subprocess):
        """When interface is down, rules saved with active=False."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()

        gateway = self._make_gateway_peer("10.0.50.0/24")
        wc = self._make_wc("wg0", "10.200.0.1/24", peers=[gateway])
        mgr.init(lambda: {"wg0": wc})

        # Interface is down
        mock_subprocess.run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")

        mgr.apply_rules("wg0")

        status = mgr.get_status_for_config("wg0")
        assert len(status) == 1
        assert status[0]["active"] is False

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_sync_all(self, mock_subprocess):
        """sync_all rebuilds rules for all configs."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()

        gw1 = self._make_gateway_peer("10.0.50.0/24")
        gw2 = self._make_gateway_peer("10.0.50.0/24")
        wc1 = self._make_wc("wg-office", "10.200.0.1/24", peers=[gw1])
        wc2 = self._make_wc("wg-home", "10.128.69.1/24", peers=[gw2])
        mgr.init(lambda: {"wg-office": wc1, "wg-home": wc2})

        def run_se(cmd, **kwargs):
            r = MagicMock(returncode=0, stdout="UP", stderr="")
            if cmd[:3] == ["ip", "rule", "del"]:
                r.returncode = 2
            return r
        mock_subprocess.run.side_effect = run_se

        mgr.sync_all()

        all_status = mgr.get_status()
        assert len(all_status) == 2
        configs = {r["config_name"] for r in all_status}
        assert configs == {"wg-office", "wg-home"}
        # Same dest but different sources
        sources = {r["source_subnet"] for r in all_status}
        assert "10.200.0.0/24" in sources
        assert "10.128.69.0/24" in sources

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_remove_rules(self, mock_subprocess):
        """remove_rules clears rules for a config."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()

        gateway = self._make_gateway_peer("10.0.50.0/24")
        wc = self._make_wc("wg0", "10.200.0.1/24", peers=[gateway])
        mgr.init(lambda: {"wg0": wc})

        def run_se(cmd, **kwargs):
            r = MagicMock(returncode=0, stdout="UP", stderr="")
            if cmd[:3] == ["ip", "rule", "del"]:
                r.returncode = 2
            return r
        mock_subprocess.run.side_effect = run_se

        mgr.apply_rules("wg0")
        assert len(mgr.get_status()) == 1

        mgr.remove_rules("wg0")
        assert len(mgr.get_status()) == 0

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_no_gateway_peers_clears_routes(self, mock_subprocess):
        """Config with no gateway peers should have no rules."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()

        regular_peer = MagicMock()
        regular_peer.is_gateway = 0
        regular_peer.allowed_ip = "10.200.0.5/32"
        wc = self._make_wc("wg0", "10.200.0.1/24", peers=[regular_peer])
        mgr.init(lambda: {"wg0": wc})

        def run_se(cmd, **kwargs):
            r = MagicMock(returncode=0, stdout="UP", stderr="")
            if cmd[:3] == ["ip", "rule", "del"]:
                r.returncode = 2
            return r
        mock_subprocess.run.side_effect = run_se

        mgr.apply_rules("wg0")
        assert len(mgr.get_status()) == 0

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_multiple_dest_subnets(self, mock_subprocess):
        """Gateway peer with multiple subnets creates multiple rules."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()

        gateway = self._make_gateway_peer("10.0.50.0/24, 10.0.60.0/24")
        wc = self._make_wc("wg0", "10.200.0.1/24", peers=[gateway])
        mgr.init(lambda: {"wg0": wc})

        def run_se(cmd, **kwargs):
            r = MagicMock(returncode=0, stdout="UP", stderr="")
            if cmd[:3] == ["ip", "rule", "del"]:
                r.returncode = 2
            return r
        mock_subprocess.run.side_effect = run_se

        mgr.apply_rules("wg0")

        status = mgr.get_status_for_config("wg0")
        assert len(status) == 2
        dests = {r["dest_subnet"] for r in status}
        assert dests == {"10.0.50.0/24", "10.0.60.0/24"}


class TestGatewayDestSubnets:

    def test_gateway_subnets_ipv6_first_address(self):
        """Config with IPv6-first address should still filter gateway subnets correctly."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        gateway = MagicMock()
        gateway.is_gateway = 1
        gateway.allowed_ip = "fd00::5/128, 10.0.50.0/24"
        wc = MagicMock()
        wc.Address = "fd00::1/64, 10.200.0.1/24"
        wc.Peers = [gateway]
        subnets = mgr._gateway_dest_subnets(wc)
        assert "10.0.50.0/24" in subnets
        # IPv6 entries should be filtered out — only IPv4 subnets for ip rule/route
        assert "fd00::5/128" not in subnets


class TestDiagnosticsIntegration:
    """Additional tests for edge cases and status API."""

    def _make_wc(self, name, address, peers=None):
        wc = MagicMock()
        wc.Name = name
        wc.Address = address
        wc.Peers = peers or []
        return wc

    def _make_gateway_peer(self, allowed_ip):
        peer = MagicMock()
        peer.is_gateway = 1
        peer.allowed_ip = allowed_ip
        return peer

    def test_apply_rules_without_init_does_nothing(self):
        """apply_rules should silently return if init() was not called."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        # No exception should be raised, no rules created
        mgr.apply_rules("wg0")
        assert mgr.get_status() == []

    def test_sync_all_without_init_does_nothing(self):
        """sync_all should silently return if init() was not called."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        mgr.sync_all()
        assert mgr.get_status() == []

    def test_remove_rules_nonexistent_config(self):
        """remove_rules on a config that has no rules should not raise."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        # Should not raise
        mgr.remove_rules("wg-nonexistent")
        assert mgr.get_status() == []

    def test_get_status_for_config_unknown(self):
        """get_status_for_config for unknown config returns empty list."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        assert mgr.get_status_for_config("wg-unknown") == []

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_on_gateway_changed_calls_apply_rules(self, mock_subprocess):
        """on_gateway_changed should rebuild rules for the given config."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()

        gateway = self._make_gateway_peer("10.0.50.0/24")
        wc = self._make_wc("wg0", "10.200.0.1/24", peers=[gateway])
        mgr.init(lambda: {"wg0": wc})

        def run_se(cmd, **kwargs):
            r = MagicMock(returncode=0, stdout="UP", stderr="")
            if cmd[:3] == ["ip", "rule", "del"]:
                r.returncode = 2
            return r
        mock_subprocess.run.side_effect = run_se

        mgr.on_gateway_changed("wg0")

        status = mgr.get_status_for_config("wg0")
        assert len(status) == 1
        assert status[0]["dest_subnet"] == "10.0.50.0/24"

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_apply_rules_config_not_found(self, mock_subprocess):
        """apply_rules with unknown config name should not crash."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        mgr.init(lambda: {"wg0": MagicMock()})
        # "wg-nonexistent" not in configs dict
        mgr.apply_rules("wg-nonexistent")
        assert mgr.get_status() == []

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_get_status_returns_all_rules(self, mock_subprocess):
        """get_status returns rules for all configs."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()

        gw1 = self._make_gateway_peer("192.168.1.0/24")
        gw2 = self._make_gateway_peer("192.168.2.0/24")
        wc1 = self._make_wc("wg-a", "10.1.0.1/24", peers=[gw1])
        wc2 = self._make_wc("wg-b", "10.2.0.1/24", peers=[gw2])
        mgr.init(lambda: {"wg-a": wc1, "wg-b": wc2})

        def run_se(cmd, **kwargs):
            r = MagicMock(returncode=0, stdout="UP", stderr="")
            if cmd[:3] == ["ip", "rule", "del"]:
                r.returncode = 2
            return r
        mock_subprocess.run.side_effect = run_se

        mgr.apply_rules("wg-a")
        mgr.apply_rules("wg-b")

        all_status = mgr.get_status()
        assert len(all_status) == 2
        config_names = {r["config_name"] for r in all_status}
        assert config_names == {"wg-a", "wg-b"}
