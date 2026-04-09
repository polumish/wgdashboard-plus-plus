# Policy Routing Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatic source-based routing so peers from each WG interface reach shared destination networks (e.g., 10.0.50.0/24) through their own tunnel, not whichever route the kernel picked first.

**Architecture:** New `PolicyRoutingManager` singleton module (same pattern as BackupScheduler) manages `ip rule`/`ip route` entries in per-interface routing tables. It auto-syncs on gateway peer changes, Dashboard startup, and backup restore. UI shows badges on gateway peers and a read-only policy routes table in settings.

**Tech Stack:** Python 3 (Flask backend), Vue 3 + Bootstrap 5 (frontend), subprocess for `ip rule`/`ip route`, threading.Lock for safety.

**Spec:** `docs/superpowers/specs/2026-04-09-policy-routing-manager-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/modules/PolicyRoutingManager.py` | Core policy routing logic — rule computation, ip rule/route shell commands, status reporting |
| Create | `src/tests/test_policy_routing.py` | Unit tests for PolicyRoutingManager |
| Modify | `src/dashboard.py:189` | Global instance declaration |
| Modify | `src/dashboard.py:337-338` | Initialize and start PolicyRoutingManager |
| Modify | `src/dashboard.py:1458-1519` | `_syncGatewaySubnetsToConfig()` — call `on_gateway_changed()` instead of `_applyPolicyRoutesLive()` |
| Modify | `src/dashboard.py:1646-1713` | Remove `_policyRoutingTableId`, `_configSubnetForPolicy`, `_applyPolicyRoutesLive`, update `API_applyPolicyRoutes` |
| Modify | `src/dashboard.py:931,988` | Add `sync_all()` after `_reload_wireguard_configurations()` in restore flows |
| Create | `src/static/app/src/components/settingsComponent/policyRoutingStatus.vue` | Read-only policy routes table for settings page |
| Modify | `src/static/app/src/views/settings.vue:41-62` | Add "Policy Routing" tab |
| Modify | `src/static/app/src/components/configurationComponents/peerRow.vue` | Add policy route badge for gateway peers |
| Modify | `src/modules/WireguardDiagnostics.py:166-240` | Add `POLICY_ROUTE_MISSING` and `POLICY_ROUTE_CONFLICT` warnings |

---

### Task 1: PolicyRoutingManager — Core Module with Tests

**Files:**
- Create: `src/modules/PolicyRoutingManager.py`
- Create: `src/tests/test_policy_routing.py`

- [ ] **Step 1: Write test file with failing tests for PolicyRule and table ID computation**

Create `src/tests/test_policy_routing.py`:

```python
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


class TestConfigSubnet:

    def test_extracts_ipv4_network(self):
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        wc = MagicMock()
        wc.Address = "10.200.0.1/24"
        assert mgr._config_subnet(wc) == "10.200.0.0/24"

    def test_skips_ipv6(self):
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        wc = MagicMock()
        wc.Address = "fd00::1/64, 10.128.69.1/24"
        assert mgr._config_subnet(wc) == "10.128.69.0/24"

    def test_returns_none_for_empty(self):
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        wc = MagicMock()
        wc.Address = ""
        assert mgr._config_subnet(wc) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_policy_routing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.PolicyRoutingManager'`

- [ ] **Step 3: Create PolicyRoutingManager module with core logic**

Create `src/modules/PolicyRoutingManager.py`:

```python
"""PolicyRoutingManager — automatic source-based routing for WG interfaces.

When multiple WG interfaces have gateway peers pointing to the same destination
network, this manager creates per-interface routing tables with ip rule/route
entries so traffic is routed based on source address.
"""
import hashlib
import ipaddress
import logging
import subprocess
import threading
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class PolicyRule:
    config_name: str
    table_id: int
    source_subnet: str
    dest_subnet: str
    device: str
    active: bool


class PolicyRoutingManager:
    """Manages policy-based routing rules for WireGuard interfaces."""

    def __init__(self):
        self._rules: dict[str, list[PolicyRule]] = {}
        self._lock = threading.Lock()
        self._configurations_fn = None  # callable returning WireguardConfigurations dict

    def init(self, configurations_fn):
        """Late-init with a callable that returns WireguardConfigurations dict."""
        self._configurations_fn = configurations_fn

    def _table_id(self, config_name: str) -> int:
        """Deterministic routing table ID 100-252 from config name."""
        h = int(hashlib.sha1(config_name.encode()).hexdigest(), 16)
        return 100 + (h % 153)

    def _config_subnet(self, wc) -> str | None:
        """Extract IPv4 network CIDR from wc.Address."""
        for addr in (a.strip() for a in (wc.Address or "").split(",")):
            if not addr:
                continue
            try:
                iface = ipaddress.ip_interface(addr)
                if iface.version == 4:
                    return str(iface.network)
            except ValueError:
                continue
        return None

    def _gateway_dest_subnets(self, wc) -> list[str]:
        """Collect destination subnets from gateway peers (is_gateway=1)."""
        config_net = None
        for addr in (a.strip() for a in (wc.Address or "").split(",")):
            try:
                config_net = ipaddress.ip_interface(addr).network
                break
            except ValueError:
                pass

        subnets = []
        for peer in wc.Peers:
            if getattr(peer, "is_gateway", 0) != 1:
                continue
            for part in (peer.allowed_ip or "").split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    net = ipaddress.ip_network(part, strict=False)
                    if config_net and net.subnet_of(config_net):
                        continue
                    subnets.append(part)
                except (ValueError, TypeError):
                    subnets.append(part)
        return subnets

    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Run a shell command, log failures."""
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 and result.stderr:
            logger.debug("cmd %s stderr: %s", " ".join(cmd), result.stderr.strip())
        return result

    def _interface_is_up(self, name: str) -> bool:
        """Check if a network interface exists and is UP."""
        result = self._run(["ip", "link", "show", name])
        return result.returncode == 0 and "UP" in result.stdout

    def apply_rules(self, config_name: str):
        """Flush and rebuild ip rule/route entries for one WG interface."""
        if self._configurations_fn is None:
            return
        configs = self._configurations_fn()
        if config_name not in configs:
            logger.warning("apply_rules: config %s not found", config_name)
            return

        wc = configs[config_name]
        source = self._config_subnet(wc)
        if not source:
            logger.warning("apply_rules: no IPv4 subnet for %s", config_name)
            return

        table_id = self._table_id(config_name)
        dest_subnets = self._gateway_dest_subnets(wc)
        is_up = self._interface_is_up(config_name)

        with self._lock:
            # Build rule objects
            rules = [
                PolicyRule(
                    config_name=config_name,
                    table_id=table_id,
                    source_subnet=source,
                    dest_subnet=dest,
                    device=config_name,
                    active=is_up,
                )
                for dest in dest_subnets
            ]
            self._rules[config_name] = rules

            if not is_up:
                logger.info("apply_rules: %s is down, rules saved but not applied", config_name)
                return

            # Flush table
            self._run(["ip", "route", "flush", "table", str(table_id)])

            # Remove old rules for this source+table
            while True:
                res = self._run(["ip", "rule", "del", "from", source, "table", str(table_id)])
                if res.returncode != 0:
                    break

            if not dest_subnets:
                logger.info("apply_rules: %s — no gateway peers, routes cleared", config_name)
                return

            # Add own subnet route
            self._run(["ip", "route", "add", source, "dev", config_name, "table", str(table_id)])

            # Add per-destination rules and routes
            for dest in dest_subnets:
                self._run([
                    "ip", "rule", "add", "from", source, "to", dest,
                    "table", str(table_id), "priority", "100",
                ])
                self._run([
                    "ip", "route", "add", dest, "dev", config_name,
                    "table", str(table_id),
                ])

            logger.info(
                "apply_rules: %s — table %d, source %s, %d destinations",
                config_name, table_id, source, len(dest_subnets),
            )

    def remove_rules(self, config_name: str):
        """Remove all policy routing rules for a WG interface."""
        with self._lock:
            rules = self._rules.pop(config_name, [])
            if not rules:
                return
            table_id = rules[0].table_id
            source = rules[0].source_subnet
            self._run(["ip", "route", "flush", "table", str(table_id)])
            while True:
                res = self._run(["ip", "rule", "del", "from", source, "table", str(table_id)])
                if res.returncode != 0:
                    break
            logger.info("remove_rules: %s — cleared table %d", config_name, table_id)

    def on_gateway_changed(self, config_name: str):
        """Called when gateway peers are added/updated/deleted. Rebuilds rules."""
        self.apply_rules(config_name)

    def sync_all(self):
        """Rebuild policy routes for all WG interfaces. Called on startup and after restore."""
        if self._configurations_fn is None:
            return
        configs = self._configurations_fn()
        logger.info("sync_all: rebuilding policy routes for %d configs", len(configs))
        for name in configs:
            self.apply_rules(name)

    def get_status(self) -> list[dict]:
        """Return all policy rules as dicts (for API/UI)."""
        with self._lock:
            result = []
            for rules in self._rules.values():
                result.extend(asdict(r) for r in rules)
            return result

    def get_status_for_config(self, config_name: str) -> list[dict]:
        """Return policy rules for one config (for API/UI badge)."""
        with self._lock:
            return [asdict(r) for r in self._rules.get(config_name, [])]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_policy_routing.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Add tests for apply_rules and sync_all (with mocked subprocess)**

Append to `src/tests/test_policy_routing.py`:

```python
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

        # Interface is up
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="UP", stderr="")

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

        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="UP", stderr="")
        # For rule del loop — always fail to break immediately
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
```

- [ ] **Step 6: Run all tests to verify they pass**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_policy_routing.py -v`
Expected: All 15 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Volumes/DATA/GIT/WGDashboard
git add src/modules/PolicyRoutingManager.py src/tests/test_policy_routing.py
git commit -m "feat: add PolicyRoutingManager module with tests

Source-based routing for WG interfaces sharing destination networks.
Manages ip rule/route entries in per-interface routing tables."
```

---

### Task 2: Integrate PolicyRoutingManager into dashboard.py

**Files:**
- Modify: `src/dashboard.py:189` (global declaration)
- Modify: `src/dashboard.py:337-338` (init + start)
- Modify: `src/dashboard.py:1458-1519` (`_syncGatewaySubnetsToConfig`)
- Modify: `src/dashboard.py:1646-1713` (remove old functions, update API endpoint)

- [ ] **Step 1: Add global instance and import**

In `src/dashboard.py`, after line 189 (`AllBackupScheduler`), add the import and global:

At the top imports section, add:
```python
from modules.PolicyRoutingManager import PolicyRoutingManager
```

After line 189:
```python
AllPolicyRouting: PolicyRoutingManager = PolicyRoutingManager()
```

- [ ] **Step 2: Initialize PolicyRoutingManager at startup**

In `src/dashboard.py`, after line 338 (`AllBackupScheduler.start()`), add:

```python
AllPolicyRouting.init(lambda: WireguardConfigurations)
AllPolicyRouting.sync_all()
app.logger.info("PolicyRoutingManager initialized and synced")
```

- [ ] **Step 3: Update `_syncGatewaySubnetsToConfig` to use PolicyRoutingManager**

In `src/dashboard.py`, replace lines 1514-1518:

Old:
```python
    # Apply policy routing live
    subnet = _configSubnetForPolicy(wc)
    if subnet and lanSubnets:
        tableId = _policyRoutingTableId(wc.Name)
        _applyPolicyRoutesLive(wc.Name, subnet, list(lanSubnets), tableId)
```

New:
```python
    # Apply policy routing live
    AllPolicyRouting.on_gateway_changed(wc.Name)
```

- [ ] **Step 4: Remove old standalone functions**

In `src/dashboard.py`, delete the following functions (lines 1646-1691):
- `_policyRoutingTableId()` (lines 1646-1650)
- `_configSubnetForPolicy()` (lines 1653-1665)
- `_applyPolicyRoutesLive()` (lines 1668-1691)

- [ ] **Step 5: Update `API_applyPolicyRoutes` endpoint**

Replace the `API_applyPolicyRoutes` function (lines 1694-1713) with:

```python
@app.post(f'{APP_PREFIX}/api/applyPolicyRoutes/<configName>')
def API_applyPolicyRoutes(configName: str):
    """Manually trigger policy routing rebuild for this config."""
    if configName not in WireguardConfigurations:
        return ResponseObject(False, "Configuration does not exist")
    AllPolicyRouting.on_gateway_changed(configName)
    return ResponseObject(True, "Policy routes applied", data={
        "rules": AllPolicyRouting.get_status_for_config(configName)
    })
```

- [ ] **Step 6: Add new API endpoints for policy routing status**

Add after the updated `API_applyPolicyRoutes`:

```python
@app.get(f'{APP_PREFIX}/api/policyRouting/status')
def API_policyRoutingStatus():
    """Return all policy routing rules across all interfaces."""
    return ResponseObject(data=AllPolicyRouting.get_status())


@app.get(f'{APP_PREFIX}/api/policyRouting/status/<configName>')
def API_policyRoutingStatusConfig(configName: str):
    """Return policy routing rules for one interface."""
    if configName not in WireguardConfigurations:
        return ResponseObject(False, "Configuration does not exist")
    return ResponseObject(data=AllPolicyRouting.get_status_for_config(configName))
```

- [ ] **Step 7: Verify dashboard still starts and tests pass**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/ -v --timeout=30`
Expected: All existing + new tests PASS

- [ ] **Step 8: Commit**

```bash
cd /Volumes/DATA/GIT/WGDashboard
git add src/dashboard.py
git commit -m "feat: integrate PolicyRoutingManager into dashboard

Replace standalone _applyPolicyRoutesLive with PolicyRoutingManager.
Add /api/policyRouting/status endpoints. Auto-sync on startup."
```

---

### Task 3: Add sync_all After Backup Restore

**Files:**
- Modify: `src/dashboard.py:931` (global restore flow)
- Modify: `src/dashboard.py:988` (per-config restore flow)

- [ ] **Step 1: Add sync_all after global restore**

In `src/dashboard.py`, after line 932 (`app.logger.info("[Restore] WG reload complete")`), add:

```python
                    AllPolicyRouting.sync_all()
                    app.logger.info("[Restore] Policy routes re-synced")
```

This goes inside the `if "configurations" in components:` block, right after `_reload_wireguard_configurations()`.

- [ ] **Step 2: Add sync_all after per-config restore**

In `src/dashboard.py`, in the `_do_config_restore` function (around line 988), after `_reload_wireguard_configurations()`, add:

```python
            AllPolicyRouting.sync_all()
```

The full function becomes:
```python
    def _do_config_restore():
        result = AllBackupManager.restoreConfigBackup(config_name, name)
        if result.get("status"):
            _reload_wireguard_configurations()
            AllPolicyRouting.sync_all()
```

- [ ] **Step 3: Commit**

```bash
cd /Volumes/DATA/GIT/WGDashboard
git add src/dashboard.py
git commit -m "feat: re-sync policy routes after backup restore

Ensures policy routing rules are rebuilt when WG configs
change due to backup restore operations."
```

---

### Task 4: Network Diagnostics — Policy Route Warnings

**Files:**
- Modify: `src/modules/WireguardDiagnostics.py:166-240`

- [ ] **Step 1: Write test for new warning types**

Append to `src/tests/test_policy_routing.py`:

```python
class TestDiagnosticsIntegration:

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_get_status_empty_when_no_gateways(self, mock_subprocess):
        """Diagnostics should see no policy rules when no gateways configured."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()
        mgr.init(lambda: {})
        mgr.sync_all()
        assert mgr.get_status() == []

    @patch("modules.PolicyRoutingManager.subprocess")
    def test_get_status_reflects_active_state(self, mock_subprocess):
        """Active flag should reflect interface state."""
        PolicyRoutingManager, _ = _import_manager()
        mgr = PolicyRoutingManager()

        gateway = MagicMock()
        gateway.is_gateway = 1
        gateway.allowed_ip = "10.0.50.0/24"
        wc = MagicMock()
        wc.Name = "wg0"
        wc.Address = "10.200.0.1/24"
        wc.Peers = [gateway]
        mgr.init(lambda: {"wg0": wc})

        # Interface down
        mock_subprocess.run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        mgr.apply_rules("wg0")

        status = mgr.get_status()
        assert len(status) == 1
        assert status[0]["active"] is False
```

- [ ] **Step 2: Run test to verify it passes (uses existing module)**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_policy_routing.py::TestDiagnosticsIntegration -v`
Expected: PASS

- [ ] **Step 3: Add policy routing warnings to WireguardDiagnostics.py**

In `src/modules/WireguardDiagnostics.py`, in the `cross_reference` method, after the existing warning checks (after line 238, before `return annotated, warnings`), add:

```python
        # Check policy routing status if PolicyRoutingManager is available
        try:
            from modules.PolicyRoutingManager import PolicyRoutingManager
            # Access the global instance via the interface's config
            # This is checked externally — we just add warning types here
        except ImportError:
            pass
```

Actually, the diagnostics warnings for policy routing are better added at the `build_snapshot` level. In `build_snapshot()` method, after the existing snapshot is built, add a hook. 

In `src/modules/WireguardDiagnostics.py`, modify `build_snapshot()` to accept an optional `policy_routing_manager` parameter:

After the existing warnings list is built (around line 270), add:

```python
        # Policy routing warnings
        if policy_status is not None:
            config_rules = [r for r in policy_status if r["config_name"] == interface]
            has_gateways = any(
                getattr(p, "is_gateway", 0) == 1
                for p in (peer_names or {}).values()
            )
            if has_gateways and not config_rules:
                warnings.append({
                    "type": "policy_route_missing",
                    "target": interface,
                    "message": f"{interface} has gateway peers but no policy routes applied",
                })
            for rule in config_rules:
                if not rule["active"]:
                    warnings.append({
                        "type": "policy_route_inactive",
                        "target": interface,
                        "message": f"Policy route {rule['source_subnet']} → {rule['dest_subnet']} exists but interface is down",
                    })
```

Update the `build_snapshot` signature to accept `policy_status: list[dict] | None = None` parameter.

- [ ] **Step 4: Update DiagnosticsMonitor to pass policy routing status**

In the `_monitor_loop` method where `build_snapshot()` is called, pass `AllPolicyRouting.get_status()` if available. This requires updating `DiagnosticsMonitor.start()` to accept the policy routing manager reference.

In `src/dashboard.py`, where `AllDiagnosticsMonitor.start()` is called (line 183), add the policy routing reference:

```python
AllDiagnosticsMonitor.start(
    lambda: WireguardConfigurations, app.logger,
    lambda: int(DashboardConfig.GetConfig("Server", "peer_handshake_threshold")[1]),
    policy_status_fn=lambda: AllPolicyRouting.get_status()
)
```

- [ ] **Step 5: Commit**

```bash
cd /Volumes/DATA/GIT/WGDashboard
git add src/modules/WireguardDiagnostics.py src/dashboard.py src/tests/test_policy_routing.py
git commit -m "feat: add policy routing warnings to network diagnostics

Shows POLICY_ROUTE_MISSING when gateway peers exist without routes,
and POLICY_ROUTE_INACTIVE when routes exist but interface is down."
```

---

### Task 5: Frontend — Policy Route Badge on Gateway Peers

**Files:**
- Modify: `src/static/app/src/components/configurationComponents/peerRow.vue`

- [ ] **Step 1: Add policy route badge to peerRow.vue**

In `src/static/app/src/components/configurationComponents/peerRow.vue`, update the script section to accept policy routing status and add the badge.

Update `<script setup>`:

```javascript
import {computed, ref, useTemplateRef} from "vue";
import PeerSettingsDropdown from "@/components/configurationComponents/peerSettingsDropdown.vue";
import {onClickOutside} from "@vueuse/core";

const props = defineProps(['Peer', 'policyRoutes'])
const subMenuOpened = ref(false)
const getLatestHandshake = computed(() => {
	if (props.Peer.latest_handshake.includes(",")){
		return props.Peer.latest_handshake.split(",")[0]
	}
	return props.Peer.latest_handshake;
})

const policyRouteActive = computed(() => {
	if (!props.policyRoutes || props.Peer.is_gateway !== 1) return null;
	const rules = props.policyRoutes.filter(r => r.config_name === props.Peer._config_name);
	if (rules.length === 0) return null;
	return rules.every(r => r.active);
})

const target = useTemplateRef('target');
onClickOutside(target, event => {
	subMenuOpened.value = false;
});

const emit = defineEmits(['qrcode', 'configurationFile', 'setting', 'jobs', 'refresh', 'share'])
```

- [ ] **Step 2: Add badge markup in template**

In the template, after the Allowed IP cell (after line 34 `{{Peer.allowed_ip}}`), add the badge inside the same `<td>` or as a new element after the name cell. Best placement is after the peer name (line 26):

Replace:
```html
<td>
    <small>{{Peer.name ? Peer.name : 'Untitled Peer'}}</small>
</td>
```

With:
```html
<td>
    <small>{{Peer.name ? Peer.name : 'Untitled Peer'}}</small>
    <span v-if="policyRouteActive === true"
          class="badge bg-success ms-1" style="font-size: 0.65em;">
        <i class="bi bi-signpost-split"></i> Policy Route
    </span>
    <span v-else-if="policyRouteActive === false"
          class="badge bg-secondary ms-1" style="font-size: 0.65em;">
        <i class="bi bi-signpost-split"></i> Policy Route Inactive
    </span>
</td>
```

- [ ] **Step 3: Pass policyRoutes prop from parent component**

Find the parent component that renders `<peerRow>` and pass the policy routing status. The parent needs to fetch `/api/policyRouting/status/<configName>` on load and pass it as a prop.

Search for where `peerRow` is used:

In the parent component (likely in `configurationComponents/`), add:

```javascript
// In setup/data:
const policyRoutes = ref([])

// On mount or when config loads:
fetchGet("/api/policyRouting/status/" + configName, {}, (res) => {
    if (res.status) policyRoutes.value = res.data;
});
```

And pass to each `<peerRow>`:
```html
<peerRow :Peer="peer" :policyRoutes="policyRoutes" ... />
```

- [ ] **Step 4: Build frontend**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src/static/app && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 5: Commit**

```bash
cd /Volumes/DATA/GIT/WGDashboard
git add src/static/app/src/components/configurationComponents/peerRow.vue
git add src/static/app/src/  # parent component changes
git commit -m "feat(ui): add policy route badge on gateway peers

Shows green 'Policy Route' badge when active, grey when inactive.
Only visible on peers with is_gateway=1."
```

---

### Task 6: Frontend — Policy Routing Status Table in Settings

**Files:**
- Create: `src/static/app/src/components/settingsComponent/policyRoutingStatus.vue`
- Modify: `src/static/app/src/views/settings.vue`

- [ ] **Step 1: Create policyRoutingStatus.vue component**

Create `src/static/app/src/components/settingsComponent/policyRoutingStatus.vue`:

```vue
<script setup>
import {ref, onMounted} from "vue";
import {fetchGet} from "@/utilities/fetch.js";

const rules = ref([])
const loading = ref(true)

function loadStatus() {
    loading.value = true
    fetchGet("/api/policyRouting/status", {}, (res) => {
        if (res.status) {
            rules.value = res.data
        }
        loading.value = false
    })
}

onMounted(loadStatus)
</script>

<template>
<div class="card shadow-sm rounded-3">
    <div class="card-header d-flex align-items-center justify-content-between">
        <h6 class="mb-0">
            <i class="bi bi-signpost-split me-2"></i>Policy Routing Rules
        </h6>
        <button class="btn btn-sm btn-outline-secondary" @click="loadStatus" :disabled="loading">
            <i class="bi bi-arrow-clockwise" :class="{'spin': loading}"></i>
        </button>
    </div>
    <div class="card-body">
        <div v-if="loading" class="text-center py-3">
            <div class="spinner-border spinner-border-sm"></div>
        </div>
        <div v-else-if="rules.length === 0" class="text-muted text-center py-3">
            <i class="bi bi-info-circle me-1"></i>
            No policy routes. Add a gateway peer to enable automatic source-based routing.
        </div>
        <div v-else class="table-responsive">
            <table class="table table-sm table-hover mb-0">
                <thead>
                    <tr>
                        <th>Source</th>
                        <th>Destination</th>
                        <th>Device</th>
                        <th>Table ID</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="rule in rules" :key="rule.config_name + rule.dest_subnet">
                        <td><code>{{ rule.source_subnet }}</code></td>
                        <td><code>{{ rule.dest_subnet }}</code></td>
                        <td>{{ rule.device }}</td>
                        <td>{{ rule.table_id }}</td>
                        <td>
                            <span v-if="rule.active" class="badge bg-success">Active</span>
                            <span v-else class="badge bg-secondary">Inactive</span>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</div>
</template>

<style scoped>
.spin {
    animation: spin 1s linear infinite;
}
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
</style>
```

- [ ] **Step 2: Add Policy Routing tab to settings.vue**

In `src/static/app/src/views/settings.vue`, add the tab entry in the `tabs` array (after the "backup" entry, around line 57):

```javascript
{
    id: "policy_routing",
    title: "Policy Routing"
},
```

Add the import:
```javascript
import PolicyRoutingStatus from "@/components/settingsComponent/policyRoutingStatus.vue";
```

And in the template, add the tab content panel (find where other tab panels are rendered and add):

```html
<div v-if="activeTab === 'policy_routing'">
    <PolicyRoutingStatus />
</div>
```

- [ ] **Step 3: Build frontend**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src/static/app && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
cd /Volumes/DATA/GIT/WGDashboard
git add src/static/app/src/components/settingsComponent/policyRoutingStatus.vue
git add src/static/app/src/views/settings.vue
git commit -m "feat(ui): add Policy Routing status table in settings

Read-only table showing all active policy routing rules across
WG interfaces with source, destination, device, table ID, and status."
```

---

### Task 7: Deploy to Staging and Test

**Files:** None (deployment task)

- [ ] **Step 1: Build frontend for deployment**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src/static/app && npm run build`

- [ ] **Step 2: Rsync to staging**

Run: `rsync -avz --delete /Volumes/DATA/GIT/WGDashboard/src/ staging:10086:/opt/WGDashboard/src/`

(Adjust rsync command to match the actual staging deployment method.)

- [ ] **Step 3: Restart WGDashboard on staging**

SSH to staging (192.168.100.161) and restart:
```bash
cd /opt/WGDashboard/src && ./wgd.sh restart
```

- [ ] **Step 4: Verify policy routing works**

On staging, test these scenarios:
1. Check Dashboard logs for "PolicyRoutingManager initialized and synced"
2. `GET /api/policyRouting/status` — should show rules for all configs with gateway peers
3. Add a gateway peer to a test config → verify rules appear automatically
4. Check `ip rule show` and `ip route show table <N>` on the server to confirm kernel state
5. Verify the Policy Routing tab in Settings shows the rules table
6. Verify gateway peers show the green "Policy Route" badge

- [ ] **Step 5: Test backup restore flow**

1. Create a backup on staging
2. Delete a gateway peer
3. Verify policy routes update (removed from status)
4. Restore from backup
5. Verify policy routes are re-synced (appear again in status)

---

### Task 8: Production Deployment

**Files:** None (deployment task)

- [ ] **Step 1: Copy production config to staging**

Copy the current production WG configs and database to staging to test with real data:
```bash
# From prod (116.203.226.32) to staging (192.168.100.161)
scp prod:/etc/wireguard/*.conf staging:/etc/wireguard/
# Copy DB dump if needed
```

- [ ] **Step 2: Test on staging with production data**

Restart WGDashboard on staging and verify:
1. All existing gateway peers get correct policy routes
2. No errors in logs
3. `ip rule show` matches expected source→table mappings
4. Policy Routing tab shows all rules correctly

- [ ] **Step 3: Deploy to production via GitLab CI**

Push to main branch, let GitLab CI pipeline deploy:
```bash
git push origin main
```

Monitor the pipeline and verify deployment succeeds.

- [ ] **Step 4: Verify on production**

1. Check Dashboard logs for successful PolicyRoutingManager init
2. `GET /api/policyRouting/status` shows correct rules
3. `ip rule show` on prod confirms source-based routing is active
4. Test actual traffic: verify peer from each network reaches 10.0.50.0/24 through its own tunnel
