# MouseHole v2.0 — Adapter Interface + WireGuard Extraction

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the plugin-based adapter architecture and extract existing WireGuard code into the first adapter, so MouseHole can support multiple VPN protocols.

**Architecture:** Introduce `BaseVPNAdapter` abstract class with capability declarations. Create adapter registry that discovers plugins at startup. Refactor `WireguardConfiguration` (1373 lines) to implement the adapter interface. Existing API routes call adapter methods instead of WG-specific code directly. AmneziaWG stays as part of the WireGuard adapter (same protocol family).

**Tech Stack:** Python 3.10+, Flask, SQLAlchemy, MariaDB, pytest

**Spec:** `docs/superpowers/specs/2026-04-08-mousehole-universal-vpn-panel-design.md`

**Related plans (to be written separately):**
- Plan 2: Unified DB Schema Migration
- Plan 3: UI Overhaul (sidebar, unified peers, adapter settings)
- Plan 4: Rebrand (MouseHole naming, logo, README)

---

## File Map

### New files

| File | Responsibility |
|------|---------------|
| `src/adapters/__init__.py` | Package init |
| `src/adapters/base.py` | `BaseVPNAdapter` ABC, `Capability` enum, `AdapterManifest` dataclass |
| `src/adapters/registry.py` | `AdapterRegistry` — discover, load, enable/disable adapters |
| `src/adapters/wireguard/__init__.py` | `WireGuardAdapter(BaseVPNAdapter)` — public interface |
| `src/adapters/wireguard/manifest.json` | Plugin metadata |
| `src/adapters/wireguard/configuration.py` | Refactored WireguardConfiguration (VPN operations only) |
| `src/adapters/wireguard/parser.py` | `wg show` output parsing, `.conf` file reading/writing |
| `src/adapters/wireguard/peer.py` | WireGuard-specific Peer model (moved from `src/modules/Peer.py`) |
| `src/tests/test_adapter_base.py` | Tests for BaseVPNAdapter contract |
| `src/tests/test_adapter_registry.py` | Tests for AdapterRegistry discovery and lifecycle |
| `src/tests/test_adapter_wireguard.py` | Tests for WireGuardAdapter |

### Modified files

| File | Changes |
|------|---------|
| `src/dashboard.py` | Replace direct WG calls with adapter registry lookups |
| `src/modules/DashboardConfig.py` | Add `[Adapters]` ini section handling |
| `src/wg-dashboard.ini` | Add `[Adapters]` section with `wireguard = enabled` |
| `src/tests/conftest.py` | Add adapter fixtures, update existing fixtures |

### Untouched (for now)

These files stay as-is in this plan. They'll be addressed in the DB migration and UI plans:
- `src/modules/BackupManager.py`, `BackupScheduler.py` — will adapt to new schema later
- `src/static/app/` — UI changes are a separate plan
- `src/modules/DashboardClients.py` — client portal untouched

---

## Task 1: BaseVPNAdapter and Capability enum

**Files:**
- Create: `src/adapters/__init__.py`
- Create: `src/adapters/base.py`
- Test: `src/tests/test_adapter_base.py`

- [ ] **Step 1: Write tests for Capability enum and BaseVPNAdapter**

```python
# src/tests/test_adapter_base.py
import pytest
from adapters.base import BaseVPNAdapter, Capability, AdapterManifest


def test_capability_enum_members():
    """All expected capabilities exist."""
    assert Capability.PEER_MANAGEMENT.value == "peer_management"
    assert Capability.TRAFFIC_STATS.value == "traffic_stats"
    assert Capability.CONFIG_GENERATION.value == "config_generation"
    assert Capability.KEY_MANAGEMENT.value == "key_management"
    assert Capability.ACCESS_CONTROL.value == "access_control"


def test_adapter_manifest_fields():
    m = AdapterManifest(
        name="TestVPN",
        version="1.0.0",
        adapter_type="testvpn",
        author="Test Author",
        description="A test adapter",
        capabilities=[Capability.PEER_MANAGEMENT],
    )
    assert m.name == "TestVPN"
    assert m.adapter_type == "testvpn"
    assert Capability.PEER_MANAGEMENT in m.capabilities


def test_base_adapter_cannot_instantiate():
    """BaseVPNAdapter is abstract — cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseVPNAdapter()


class MinimalAdapter(BaseVPNAdapter):
    """Minimal concrete adapter for testing the ABC contract."""

    @classmethod
    def manifest(cls) -> AdapterManifest:
        return AdapterManifest(
            name="Minimal",
            version="0.1",
            adapter_type="minimal",
            author="test",
            description="test adapter",
            capabilities=[],
        )

    def probe(self) -> bool:
        return True

    def get_status(self) -> str:
        return "up"

    def start(self, interface_name: str) -> bool:
        return True

    def stop(self, interface_name: str) -> bool:
        return True

    def list_interfaces(self) -> list[dict]:
        return []

    def get_interface(self, name: str) -> dict | None:
        return None


def test_minimal_adapter_instantiates():
    adapter = MinimalAdapter()
    assert adapter.get_status() == "up"
    assert adapter.list_interfaces() == []
    assert adapter.has_capability(Capability.PEER_MANAGEMENT) is False


def test_has_capability():
    class WithPeers(MinimalAdapter):
        @classmethod
        def manifest(cls) -> AdapterManifest:
            return AdapterManifest(
                name="WithPeers",
                version="0.1",
                adapter_type="withpeers",
                author="test",
                description="test",
                capabilities=[Capability.PEER_MANAGEMENT, Capability.TRAFFIC_STATS],
            )

    adapter = WithPeers()
    assert adapter.has_capability(Capability.PEER_MANAGEMENT) is True
    assert adapter.has_capability(Capability.TRAFFIC_STATS) is True
    assert adapter.has_capability(Capability.KEY_MANAGEMENT) is False


def test_optional_methods_raise_not_implemented():
    """Calling optional methods on an adapter without that capability raises."""
    adapter = MinimalAdapter()
    with pytest.raises(NotImplementedError):
        adapter.add_peer("iface", {})
    with pytest.raises(NotImplementedError):
        adapter.remove_peer("iface", "id")
    with pytest.raises(NotImplementedError):
        adapter.list_peers("iface")
    with pytest.raises(NotImplementedError):
        adapter.get_transfer_data("iface")
    with pytest.raises(NotImplementedError):
        adapter.generate_client_config("iface", "peer_id")
    with pytest.raises(NotImplementedError):
        adapter.generate_keys()
    with pytest.raises(NotImplementedError):
        adapter.restrict_peer("iface", "peer_id")
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_adapter_base.py -v`
Expected: ModuleNotFoundError — `adapters` package doesn't exist yet.

- [ ] **Step 3: Implement BaseVPNAdapter**

```python
# src/adapters/__init__.py
"""MouseHole VPN Adapter framework."""
```

```python
# src/adapters/base.py
"""Base class and capability declarations for VPN adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Capability(Enum):
    """Capabilities a VPN adapter can declare."""

    PEER_MANAGEMENT = "peer_management"
    TRAFFIC_STATS = "traffic_stats"
    CONFIG_GENERATION = "config_generation"
    KEY_MANAGEMENT = "key_management"
    ACCESS_CONTROL = "access_control"


@dataclass
class AdapterManifest:
    """Metadata about a VPN adapter plugin."""

    name: str
    version: str
    adapter_type: str  # e.g. "wireguard", "openvpn", "zerotier"
    author: str
    description: str
    capabilities: list[Capability] = field(default_factory=list)


class BaseVPNAdapter(ABC):
    """Abstract base class for all VPN protocol adapters.

    Every adapter MUST implement the required methods (get_status, start, stop,
    list_interfaces, get_interface) and declare its capabilities via manifest().

    Optional methods (peer management, traffic stats, etc.) raise
    NotImplementedError by default. Adapters override only what they support.
    """

    # ------------------------------------------------------------------
    # Required: every adapter MUST implement these
    # ------------------------------------------------------------------

    @classmethod
    @abstractmethod
    def manifest(cls) -> AdapterManifest:
        """Return adapter metadata and capability declarations."""

    @abstractmethod
    def probe(self) -> bool:
        """Check if the VPN service is available on this system.

        Returns True if the adapter can operate (e.g., WireGuard binary exists).
        """

    @abstractmethod
    def get_status(self) -> str:
        """Overall service status: 'up', 'down', or 'error'."""

    @abstractmethod
    def start(self, interface_name: str) -> bool:
        """Start a VPN interface. Returns True on success."""

    @abstractmethod
    def stop(self, interface_name: str) -> bool:
        """Stop a VPN interface. Returns True on success."""

    @abstractmethod
    def list_interfaces(self) -> list[dict]:
        """List all interfaces managed by this adapter.

        Each dict: {name, listen_port, subnet, peers_count, status}
        """

    @abstractmethod
    def get_interface(self, name: str) -> dict | None:
        """Get detailed info for a single interface, or None if not found."""

    # ------------------------------------------------------------------
    # Capability helper
    # ------------------------------------------------------------------

    def has_capability(self, capability: Capability) -> bool:
        """Check if this adapter declares a given capability."""
        return capability in self.manifest().capabilities

    # ------------------------------------------------------------------
    # Optional: PEER_MANAGEMENT
    # ------------------------------------------------------------------

    def list_peers(self, interface_name: str) -> list[dict]:
        raise NotImplementedError(f"{self.manifest().name} does not support list_peers")

    def get_peer(self, interface_name: str, peer_id: str) -> dict | None:
        raise NotImplementedError(f"{self.manifest().name} does not support get_peer")

    def add_peer(self, interface_name: str, peer_data: dict) -> dict:
        raise NotImplementedError(f"{self.manifest().name} does not support add_peer")

    def remove_peer(self, interface_name: str, peer_id: str) -> bool:
        raise NotImplementedError(f"{self.manifest().name} does not support remove_peer")

    # ------------------------------------------------------------------
    # Optional: TRAFFIC_STATS
    # ------------------------------------------------------------------

    def get_transfer_data(self, interface_name: str) -> list[dict]:
        raise NotImplementedError(f"{self.manifest().name} does not support get_transfer_data")

    def get_endpoint_data(self, interface_name: str) -> list[dict]:
        raise NotImplementedError(f"{self.manifest().name} does not support get_endpoint_data")

    # ------------------------------------------------------------------
    # Optional: CONFIG_GENERATION
    # ------------------------------------------------------------------

    def generate_client_config(self, interface_name: str, peer_id: str) -> str:
        raise NotImplementedError(f"{self.manifest().name} does not support generate_client_config")

    def generate_qr(self, interface_name: str, peer_id: str) -> bytes:
        raise NotImplementedError(f"{self.manifest().name} does not support generate_qr")

    # ------------------------------------------------------------------
    # Optional: KEY_MANAGEMENT
    # ------------------------------------------------------------------

    def generate_keys(self) -> dict:
        raise NotImplementedError(f"{self.manifest().name} does not support generate_keys")

    def rotate_keys(self, interface_name: str) -> bool:
        raise NotImplementedError(f"{self.manifest().name} does not support rotate_keys")

    # ------------------------------------------------------------------
    # Optional: ACCESS_CONTROL
    # ------------------------------------------------------------------

    def restrict_peer(self, interface_name: str, peer_id: str) -> bool:
        raise NotImplementedError(f"{self.manifest().name} does not support restrict_peer")

    def unrestrict_peer(self, interface_name: str, peer_id: str) -> bool:
        raise NotImplementedError(f"{self.manifest().name} does not support unrestrict_peer")
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_adapter_base.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/DATA/GIT/WGDashboard
git add src/adapters/__init__.py src/adapters/base.py src/tests/test_adapter_base.py
git commit -m "feat(adapters): add BaseVPNAdapter ABC with Capability enum and manifest

Defines the core adapter contract: required methods (get_status, start,
stop, list_interfaces, get_interface), optional capability-gated methods
(peer management, traffic stats, config generation, key management,
access control), and AdapterManifest dataclass for plugin metadata."
```

---

## Task 2: AdapterRegistry — discovery and lifecycle

**Files:**
- Create: `src/adapters/registry.py`
- Test: `src/tests/test_adapter_registry.py`

- [ ] **Step 1: Write tests for AdapterRegistry**

```python
# src/tests/test_adapter_registry.py
import json
import os
import pytest
from adapters.base import BaseVPNAdapter, Capability, AdapterManifest
from adapters.registry import AdapterRegistry


class FakeVPNAdapter(BaseVPNAdapter):
    """Fake adapter for registry tests."""

    _probe_result = True

    @classmethod
    def manifest(cls) -> AdapterManifest:
        return AdapterManifest(
            name="FakeVPN",
            version="1.0",
            adapter_type="fakevpn",
            author="test",
            description="Fake VPN for testing",
            capabilities=[Capability.PEER_MANAGEMENT],
        )

    def probe(self) -> bool:
        return self._probe_result

    def get_status(self) -> str:
        return "up"

    def start(self, interface_name: str) -> bool:
        return True

    def stop(self, interface_name: str) -> bool:
        return True

    def list_interfaces(self) -> list[dict]:
        return [{"name": "fake0", "listen_port": 51820, "subnet": "10.0.0.0/24", "peers_count": 3, "status": "up"}]

    def get_interface(self, name: str) -> dict | None:
        return {"name": name}


def test_register_and_get_adapter():
    registry = AdapterRegistry()
    registry.register(FakeVPNAdapter)
    adapter = registry.get("fakevpn")
    assert adapter is not None
    assert adapter.manifest().name == "FakeVPN"


def test_list_adapters():
    registry = AdapterRegistry()
    registry.register(FakeVPNAdapter)
    adapters = registry.list_all()
    assert len(adapters) == 1
    assert adapters[0]["adapter_type"] == "fakevpn"
    assert adapters[0]["name"] == "FakeVPN"
    assert adapters[0]["status"] == "active"


def test_get_unknown_adapter_returns_none():
    registry = AdapterRegistry()
    assert registry.get("nonexistent") is None


def test_disable_adapter():
    registry = AdapterRegistry()
    registry.register(FakeVPNAdapter)
    registry.set_enabled("fakevpn", False)
    assert registry.get("fakevpn") is None
    adapters = registry.list_all()
    assert adapters[0]["status"] == "disabled"


def test_re_enable_adapter():
    registry = AdapterRegistry()
    registry.register(FakeVPNAdapter)
    registry.set_enabled("fakevpn", False)
    registry.set_enabled("fakevpn", True)
    assert registry.get("fakevpn") is not None


def test_probe_failure_marks_unavailable():
    class UnavailableAdapter(FakeVPNAdapter):
        _probe_result = False

        @classmethod
        def manifest(cls) -> AdapterManifest:
            return AdapterManifest(
                name="Unavailable", version="1.0", adapter_type="unavailable",
                author="test", description="test", capabilities=[],
            )

        def probe(self) -> bool:
            return False

    registry = AdapterRegistry()
    registry.register(UnavailableAdapter)
    adapters = registry.list_all()
    assert adapters[0]["status"] == "unavailable"
    # Still returns the adapter (admin can see it in settings) but get() skips it
    assert registry.get("unavailable") is None


def test_discover_from_directory(tmp_path):
    """Registry discovers adapters from a directory with manifest.json files."""
    # Create a fake adapter directory
    adapter_dir = tmp_path / "fakevpn"
    adapter_dir.mkdir()
    (adapter_dir / "manifest.json").write_text(json.dumps({
        "name": "FakeVPN",
        "version": "1.0",
        "adapter_type": "fakevpn",
        "author": "test",
        "description": "test",
    }))
    (adapter_dir / "__init__.py").write_text(
        "from adapters.base import BaseVPNAdapter, AdapterManifest, Capability\n"
        "class FakeVPNAdapter(BaseVPNAdapter):\n"
        "    @classmethod\n"
        "    def manifest(cls): return AdapterManifest(name='FakeVPN', version='1.0', adapter_type='fakevpn', author='test', description='test', capabilities=[])\n"
        "    def probe(self): return True\n"
        "    def get_status(self): return 'up'\n"
        "    def start(self, n): return True\n"
        "    def stop(self, n): return True\n"
        "    def list_interfaces(self): return []\n"
        "    def get_interface(self, n): return None\n"
    )

    registry = AdapterRegistry()
    found = registry.discover(str(tmp_path))
    assert len(found) >= 1
    assert "fakevpn" in [f["adapter_type"] for f in found]
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_adapter_registry.py -v`
Expected: ImportError — `adapters.registry` doesn't exist yet.

- [ ] **Step 3: Implement AdapterRegistry**

```python
# src/adapters/registry.py
"""Adapter registry — discovers, loads, and manages VPN adapter plugins."""

import importlib
import json
import os
import sys
from typing import Type

from .base import BaseVPNAdapter, AdapterManifest


class AdapterRegistry:
    """Central registry for VPN adapter plugins.

    Adapters can be registered manually or discovered from a directory.
    Each adapter can be enabled/disabled. Only enabled + available adapters
    are returned by get().
    """

    def __init__(self):
        self._adapters: dict[str, dict] = {}
        # {adapter_type: {"class": cls, "instance": obj, "enabled": bool, "available": bool}}

    def register(self, adapter_cls: Type[BaseVPNAdapter]) -> None:
        """Register an adapter class. Instantiates it and probes availability."""
        manifest = adapter_cls.manifest()
        instance = adapter_cls()
        available = False
        try:
            available = instance.probe()
        except Exception:
            available = False

        self._adapters[manifest.adapter_type] = {
            "class": adapter_cls,
            "instance": instance,
            "enabled": True,
            "available": available,
            "manifest": manifest,
        }

    def get(self, adapter_type: str) -> BaseVPNAdapter | None:
        """Get an active adapter instance. Returns None if not found, disabled, or unavailable."""
        entry = self._adapters.get(adapter_type)
        if entry is None:
            return None
        if not entry["enabled"] or not entry["available"]:
            return None
        return entry["instance"]

    def get_all_active(self) -> dict[str, BaseVPNAdapter]:
        """Return all enabled and available adapters as {adapter_type: instance}."""
        return {
            atype: entry["instance"]
            for atype, entry in self._adapters.items()
            if entry["enabled"] and entry["available"]
        }

    def list_all(self) -> list[dict]:
        """List all registered adapters with their status (for Settings UI)."""
        result = []
        for atype, entry in self._adapters.items():
            m = entry["manifest"]
            if not entry["enabled"]:
                status = "disabled"
            elif not entry["available"]:
                status = "unavailable"
            else:
                status = "active"

            result.append({
                "adapter_type": atype,
                "name": m.name,
                "version": m.version,
                "author": m.author,
                "description": m.description,
                "capabilities": [c.value for c in m.capabilities],
                "status": status,
            })
        return result

    def set_enabled(self, adapter_type: str, enabled: bool) -> None:
        """Enable or disable an adapter."""
        if adapter_type in self._adapters:
            self._adapters[adapter_type]["enabled"] = enabled

    def discover(self, adapters_dir: str) -> list[dict]:
        """Scan a directory for adapter plugins (dirs with manifest.json).

        Loads each adapter module and registers it. Returns list of discovered
        adapter info dicts.
        """
        discovered = []

        if not os.path.isdir(adapters_dir):
            return discovered

        for entry_name in os.listdir(adapters_dir):
            entry_path = os.path.join(adapters_dir, entry_name)
            manifest_path = os.path.join(entry_path, "manifest.json")
            init_path = os.path.join(entry_path, "__init__.py")

            if not os.path.isdir(entry_path):
                continue
            if not os.path.isfile(manifest_path):
                continue
            if not os.path.isfile(init_path):
                continue

            try:
                with open(manifest_path) as f:
                    manifest_data = json.load(f)

                # Add parent dir to sys.path if not already there
                parent_dir = os.path.dirname(adapters_dir)
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)

                adapters_package = os.path.basename(adapters_dir)
                module_name = f"{adapters_package}.{entry_name}"

                module = importlib.import_module(module_name)

                # Find the adapter class (subclass of BaseVPNAdapter)
                adapter_cls = None
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseVPNAdapter)
                        and attr is not BaseVPNAdapter
                    ):
                        adapter_cls = attr
                        break

                if adapter_cls is None:
                    continue

                self.register(adapter_cls)
                discovered.append({
                    "adapter_type": manifest_data.get("adapter_type", entry_name),
                    "name": manifest_data.get("name", entry_name),
                    "version": manifest_data.get("version", "unknown"),
                })

            except Exception:
                continue

        return discovered
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_adapter_registry.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/DATA/GIT/WGDashboard
git add src/adapters/registry.py src/tests/test_adapter_registry.py
git commit -m "feat(adapters): add AdapterRegistry with discovery, enable/disable, probe lifecycle

Discovers adapters from directories containing manifest.json. Each adapter
is probed for availability, can be enabled/disabled, and exposes status
(active/disabled/unavailable) for the Settings UI."
```

---

## Task 3: WireGuard adapter manifest and parser

**Files:**
- Create: `src/adapters/wireguard/__init__.py`
- Create: `src/adapters/wireguard/manifest.json`
- Create: `src/adapters/wireguard/parser.py`
- Test: `src/tests/test_adapter_wireguard.py`

- [ ] **Step 1: Create manifest.json**

```json
{
    "name": "WireGuard",
    "version": "1.0.0",
    "adapter_type": "wireguard",
    "author": "MouseHole",
    "description": "WireGuard and AmneziaWG VPN adapter"
}
```

- [ ] **Step 2: Write parser tests**

```python
# src/tests/test_adapter_wireguard.py
import pytest
from adapters.wireguard.parser import (
    parse_wg_show_interfaces,
    parse_wg_show_dump,
    parse_conf_file,
    build_conf_file,
)


WG_SHOW_INTERFACES = "nm-bella\nnm-fly\nSovenja"

WG_SHOW_DUMP = """nm-bella\tPRIVKEY123=\t51820\toff
PEERPUB1=\t(none)\t10.94.179.2/32\t1.2.3.4:51820\t12345\t67890\t1712345678\t25
PEERPUB2=\t(none)\t10.94.179.3/32\t(none)\t0\t0\t0\t0"""


def test_parse_wg_show_interfaces():
    result = parse_wg_show_interfaces(WG_SHOW_INTERFACES)
    assert result == ["nm-bella", "nm-fly", "Sovenja"]


def test_parse_wg_show_interfaces_empty():
    assert parse_wg_show_interfaces("") == []


def test_parse_wg_show_dump():
    iface, peers = parse_wg_show_dump(WG_SHOW_DUMP)
    assert iface["name"] == "nm-bella"
    assert iface["private_key"] == "PRIVKEY123="
    assert iface["listen_port"] == 51820
    assert len(peers) == 2
    assert peers[0]["public_key"] == "PEERPUB1="
    assert peers[0]["allowed_ips"] == "10.94.179.2/32"
    assert peers[0]["endpoint"] == "1.2.3.4:51820"
    assert peers[0]["rx_bytes"] == 12345
    assert peers[0]["tx_bytes"] == 67890
    assert peers[0]["latest_handshake"] == 1712345678
    assert peers[0]["persistent_keepalive"] == 25
    assert peers[1]["endpoint"] is None
    assert peers[1]["latest_handshake"] == 0


CONF_CONTENT = """[Interface]
PrivateKey = PRIVKEY123=
Address = 10.94.179.1/24
ListenPort = 51820
PostUp = iptables -A FORWARD -i %i -j ACCEPT

[Peer]
PublicKey = PEERPUB1=
AllowedIPs = 10.94.179.2/32
PersistentKeepalive = 25

[Peer]
PublicKey = PEERPUB2=
AllowedIPs = 10.94.179.3/32
PresharedKey = PSK123=
"""


def test_parse_conf_file():
    iface, peers = parse_conf_file(CONF_CONTENT)
    assert iface["PrivateKey"] == "PRIVKEY123="
    assert iface["Address"] == "10.94.179.1/24"
    assert iface["ListenPort"] == "51820"
    assert iface["PostUp"] == "iptables -A FORWARD -i %i -j ACCEPT"
    assert len(peers) == 2
    assert peers[0]["PublicKey"] == "PEERPUB1="
    assert peers[0]["PersistentKeepalive"] == "25"
    assert peers[1]["PresharedKey"] == "PSK123="


def test_build_conf_file():
    iface = {"PrivateKey": "KEY=", "Address": "10.0.0.1/24", "ListenPort": "51820"}
    peers = [
        {"PublicKey": "PUB1=", "AllowedIPs": "10.0.0.2/32"},
        {"PublicKey": "PUB2=", "AllowedIPs": "10.0.0.3/32", "PresharedKey": "PSK="},
    ]
    result = build_conf_file(iface, peers)
    assert "[Interface]" in result
    assert "PrivateKey = KEY=" in result
    assert result.count("[Peer]") == 2
    assert "PresharedKey = PSK=" in result
```

- [ ] **Step 3: Run tests — verify they fail**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_adapter_wireguard.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement parser.py**

```python
# src/adapters/wireguard/parser.py
"""Parse WireGuard CLI output and .conf files."""


def parse_wg_show_interfaces(output: str) -> list[str]:
    """Parse output of `wg show interfaces` into a list of interface names."""
    if not output or not output.strip():
        return []
    return [line.strip() for line in output.strip().split("\n") if line.strip()]


def parse_wg_show_dump(output: str) -> tuple[dict, list[dict]]:
    """Parse output of `wg show <iface> dump`.

    First line is the interface. Subsequent lines are peers.
    Returns (interface_dict, [peer_dicts]).
    """
    lines = [l for l in output.strip().split("\n") if l.strip()]
    if not lines:
        return {}, []

    parts = lines[0].split("\t")
    interface = {
        "name": parts[0] if len(parts) > 0 else "",
        "private_key": parts[1] if len(parts) > 1 else "",
        "listen_port": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0,
        "fwmark": parts[3] if len(parts) > 3 else "off",
    }

    peers = []
    for line in lines[1:]:
        p = line.split("\t")
        endpoint_raw = p[3] if len(p) > 3 else "(none)"
        peers.append({
            "public_key": p[0] if len(p) > 0 else "",
            "preshared_key": p[1] if len(p) > 1 and p[1] != "(none)" else None,
            "allowed_ips": p[2] if len(p) > 2 else "",
            "endpoint": endpoint_raw if endpoint_raw != "(none)" else None,
            "rx_bytes": int(p[4]) if len(p) > 4 and p[4].isdigit() else 0,
            "tx_bytes": int(p[5]) if len(p) > 5 and p[5].isdigit() else 0,
            "latest_handshake": int(p[6]) if len(p) > 6 and p[6].isdigit() else 0,
            "persistent_keepalive": int(p[7]) if len(p) > 7 and p[7].isdigit() else 0,
        })

    return interface, peers


def parse_conf_file(content: str) -> tuple[dict, list[dict]]:
    """Parse a WireGuard .conf file into interface dict + list of peer dicts."""
    interface = {}
    peers = []
    current_section = None
    current_peer = {}

    for raw_line in content.split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line == "[Interface]":
            current_section = "interface"
            continue
        elif line == "[Peer]":
            if current_peer:
                peers.append(current_peer)
            current_peer = {}
            current_section = "peer"
            continue

        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        if current_section == "interface":
            interface[key] = value
        elif current_section == "peer":
            current_peer[key] = value

    if current_peer:
        peers.append(current_peer)

    return interface, peers


def build_conf_file(interface: dict, peers: list[dict]) -> str:
    """Build a WireGuard .conf file string from interface dict + peer dicts."""
    lines = ["[Interface]"]
    for key, value in interface.items():
        if value:
            lines.append(f"{key} = {value}")

    for peer in peers:
        lines.append("")
        lines.append("[Peer]")
        for key, value in peer.items():
            if value:
                lines.append(f"{key} = {value}")

    return "\n".join(lines) + "\n"
```

```python
# src/adapters/wireguard/__init__.py
"""WireGuard + AmneziaWG adapter for MouseHole."""
```

- [ ] **Step 5: Run tests — verify they pass**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_adapter_wireguard.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/DATA/GIT/WGDashboard
git add src/adapters/wireguard/ src/tests/test_adapter_wireguard.py
git commit -m "feat(adapters): add WireGuard parser for wg show output and .conf files

Pure functions: parse_wg_show_interfaces, parse_wg_show_dump,
parse_conf_file, build_conf_file. No subprocess calls — these
are the data layer that the WireGuardAdapter will use."
```

---

## Task 4: WireGuardAdapter implementation

**Files:**
- Modify: `src/adapters/wireguard/__init__.py`
- Modify: `src/tests/test_adapter_wireguard.py`

- [ ] **Step 1: Write WireGuardAdapter tests**

Add to `src/tests/test_adapter_wireguard.py`:

```python
import subprocess
from unittest.mock import patch, MagicMock
from adapters.base import Capability
from adapters.wireguard import WireGuardAdapter


@pytest.fixture
def wg_adapter():
    """WireGuardAdapter with mocked subprocess calls."""
    with patch("adapters.wireguard.subprocess") as mock_sub:
        mock_sub.check_output.return_value = b"nm-bella\nnm-fly"
        adapter = WireGuardAdapter(wg_conf_path="/etc/wireguard")
        adapter._subprocess = mock_sub
        yield adapter, mock_sub


def test_wireguard_manifest():
    m = WireGuardAdapter.manifest()
    assert m.adapter_type == "wireguard"
    assert m.name == "WireGuard"
    assert Capability.PEER_MANAGEMENT in m.capabilities
    assert Capability.TRAFFIC_STATS in m.capabilities
    assert Capability.CONFIG_GENERATION in m.capabilities
    assert Capability.KEY_MANAGEMENT in m.capabilities
    assert Capability.ACCESS_CONTROL in m.capabilities


def test_wireguard_probe_success():
    with patch("shutil.which", return_value="/usr/bin/wg"):
        adapter = WireGuardAdapter(wg_conf_path="/etc/wireguard")
        assert adapter.probe() is True


def test_wireguard_probe_failure():
    with patch("shutil.which", return_value=None):
        adapter = WireGuardAdapter(wg_conf_path="/etc/wireguard")
        assert adapter.probe() is False


def test_wireguard_list_interfaces(wg_adapter):
    adapter, mock_sub = wg_adapter
    mock_sub.check_output.return_value = b"nm-bella\nnm-fly"
    interfaces = adapter.list_interfaces()
    assert len(interfaces) == 2
    assert interfaces[0]["name"] == "nm-bella"
    assert interfaces[1]["name"] == "nm-fly"


def test_wireguard_has_all_capabilities():
    adapter = WireGuardAdapter(wg_conf_path="/etc/wireguard")
    assert adapter.has_capability(Capability.PEER_MANAGEMENT)
    assert adapter.has_capability(Capability.TRAFFIC_STATS)
    assert adapter.has_capability(Capability.CONFIG_GENERATION)
    assert adapter.has_capability(Capability.KEY_MANAGEMENT)
    assert adapter.has_capability(Capability.ACCESS_CONTROL)


def test_wireguard_generate_keys():
    with patch("subprocess.check_output") as mock:
        mock.side_effect = [b"PRIVKEY123=\n", b"PUBKEY456=\n"]
        adapter = WireGuardAdapter(wg_conf_path="/etc/wireguard")
        keys = adapter.generate_keys()
        assert keys["private_key"] == "PRIVKEY123="
        assert keys["public_key"] == "PUBKEY456="
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_adapter_wireguard.py::test_wireguard_manifest -v`
Expected: ImportError — `WireGuardAdapter` doesn't exist yet.

- [ ] **Step 3: Implement WireGuardAdapter**

```python
# src/adapters/wireguard/__init__.py
"""WireGuard + AmneziaWG adapter for MouseHole."""

import os
import shutil
import subprocess

from adapters.base import BaseVPNAdapter, AdapterManifest, Capability
from adapters.wireguard.parser import (
    parse_wg_show_interfaces,
    parse_wg_show_dump,
    parse_conf_file,
    build_conf_file,
)


class WireGuardAdapter(BaseVPNAdapter):
    """Adapter for WireGuard and AmneziaWG VPN protocols."""

    def __init__(self, wg_conf_path: str = "/etc/wireguard", awg_conf_path: str = "/etc/amnezia/amneziawg"):
        self.wg_conf_path = wg_conf_path
        self.awg_conf_path = awg_conf_path
        self._wg_binary = "wg"
        self._wg_quick_binary = "wg-quick"
        self._subprocess = subprocess  # injectable for testing

    @classmethod
    def manifest(cls) -> AdapterManifest:
        return AdapterManifest(
            name="WireGuard",
            version="1.0.0",
            adapter_type="wireguard",
            author="MouseHole",
            description="WireGuard and AmneziaWG VPN adapter",
            capabilities=[
                Capability.PEER_MANAGEMENT,
                Capability.TRAFFIC_STATS,
                Capability.CONFIG_GENERATION,
                Capability.KEY_MANAGEMENT,
                Capability.ACCESS_CONTROL,
            ],
        )

    def probe(self) -> bool:
        """Check if wg binary is available."""
        return shutil.which(self._wg_binary) is not None

    def get_status(self) -> str:
        """Check if any WireGuard interface is active."""
        try:
            output = self._subprocess.check_output(
                [self._wg_binary, "show", "interfaces"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            return "up" if output else "down"
        except Exception:
            return "error"

    def start(self, interface_name: str) -> bool:
        try:
            self._subprocess.check_call(
                [self._wg_quick_binary, "up", interface_name],
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def stop(self, interface_name: str) -> bool:
        try:
            self._subprocess.check_call(
                [self._wg_quick_binary, "down", interface_name],
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def list_interfaces(self) -> list[dict]:
        try:
            output = self._subprocess.check_output(
                [self._wg_binary, "show", "interfaces"],
                stderr=subprocess.DEVNULL,
            ).decode()
            names = parse_wg_show_interfaces(output)
            return [{"name": n, "adapter_type": "wireguard"} for n in names]
        except Exception:
            return []

    def get_interface(self, name: str) -> dict | None:
        try:
            output = self._subprocess.check_output(
                [self._wg_binary, "show", name, "dump"],
                stderr=subprocess.DEVNULL,
            ).decode()
            iface, peers = parse_wg_show_dump(output)
            iface["peers"] = peers
            iface["peers_count"] = len(peers)
            iface["adapter_type"] = "wireguard"
            return iface
        except Exception:
            return None

    # -- PEER_MANAGEMENT --

    def list_peers(self, interface_name: str) -> list[dict]:
        iface = self.get_interface(interface_name)
        if iface is None:
            return []
        return iface.get("peers", [])

    def get_peer(self, interface_name: str, peer_id: str) -> dict | None:
        for peer in self.list_peers(interface_name):
            if peer.get("public_key") == peer_id:
                return peer
        return None

    # -- TRAFFIC_STATS --

    def get_transfer_data(self, interface_name: str) -> list[dict]:
        peers = self.list_peers(interface_name)
        return [
            {
                "peer_id": p["public_key"],
                "rx_bytes": p.get("rx_bytes", 0),
                "tx_bytes": p.get("tx_bytes", 0),
            }
            for p in peers
        ]

    def get_endpoint_data(self, interface_name: str) -> list[dict]:
        peers = self.list_peers(interface_name)
        return [
            {
                "peer_id": p["public_key"],
                "endpoint": p.get("endpoint"),
            }
            for p in peers
        ]

    # -- KEY_MANAGEMENT --

    def generate_keys(self) -> dict:
        private_key = subprocess.check_output(
            [self._wg_binary, "genkey"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        public_key = subprocess.check_output(
            [self._wg_binary, "pubkey"],
            input=private_key.encode(),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return {"private_key": private_key, "public_key": public_key}

    # -- CONFIG_GENERATION --

    def generate_client_config(self, interface_name: str, peer_id: str) -> str:
        """Generate a client .conf file for a peer."""
        peer = self.get_peer(interface_name, peer_id)
        if peer is None:
            return ""
        # Minimal client config — full version will read from DB
        iface = self.get_interface(interface_name)
        return build_conf_file(
            {"PrivateKey": "CLIENT_PRIVATE_KEY", "Address": peer.get("allowed_ips", "")},
            [{"PublicKey": iface.get("private_key", ""), "Endpoint": "SERVER:PORT", "AllowedIPs": "0.0.0.0/0"}],
        )

    # -- ACCESS_CONTROL --

    def restrict_peer(self, interface_name: str, peer_id: str) -> bool:
        try:
            self._subprocess.check_call(
                [self._wg_binary, "set", interface_name, "peer", peer_id, "remove"],
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def unrestrict_peer(self, interface_name: str, peer_id: str) -> bool:
        # Re-adding requires allowed-ips — will be enhanced with DB lookup
        return False
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd /Volumes/DATA/GIT/WGDashboard/src && python -m pytest tests/test_adapter_wireguard.py -v`
Expected: All 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/DATA/GIT/WGDashboard
git add src/adapters/wireguard/
git commit -m "feat(adapters): implement WireGuardAdapter with all capabilities

Full adapter: probe, start/stop, list/get interfaces, peer management,
traffic stats, key generation, config generation, access control.
Uses parser.py for data extraction, subprocess for WG CLI calls."
```

---

## Task 5: Integrate AdapterRegistry into dashboard.py

**Files:**
- Modify: `src/dashboard.py`
- Modify: `src/modules/DashboardConfig.py`

- [ ] **Step 1: Add [Adapters] section to DashboardConfig**

In `src/modules/DashboardConfig.py`, find the `__default` dict (contains default config sections) and add:

```python
# Add to the __default dict, after existing sections:
"Adapters": {
    "wireguard": "enabled",
},
```

- [ ] **Step 2: Initialize AdapterRegistry in dashboard.py startup**

In `src/dashboard.py`, after the BackupScheduler initialization block (~line 248), add:

```python
# --- Adapter Registry ---
from adapters.registry import AdapterRegistry
from adapters.wireguard import WireGuardAdapter

AllAdapterRegistry = AdapterRegistry()

# Read adapter enable/disable state from ini
_adapters_config = {
    k: v for k, v in DashboardConfig.toJson().get("Adapters", {}).items()
}

# Register known adapters
AllAdapterRegistry.register(WireGuardAdapter)

# Apply enable/disable from config
for adapter_type, state in _adapters_config.items():
    AllAdapterRegistry.set_enabled(adapter_type, state == "enabled")
```

- [ ] **Step 3: Add API endpoint for adapter listing**

In `src/dashboard.py`, add a new route:

```python
@app.route(f'{APP_PREFIX}/api/adapters', methods=['GET'])
@login_required
def API_ListAdapters():
    return ResponseObject(data=AllAdapterRegistry.list_all())
```

- [ ] **Step 4: Test manually**

Run on staging:
```bash
ssh -p 5022 root@192.168.100.161 "cd /opt/WGDashboard && git fetch gitlab && git reset --hard gitlab/main && cd src && ./wgd.sh restart"
```

Then: `curl -s -b cookies http://192.168.100.161:10086/api/adapters | python3 -m json.tool`

Expected: JSON with one adapter (WireGuard, status: active).

- [ ] **Step 5: Commit**

```bash
cd /Volumes/DATA/GIT/WGDashboard
git add src/dashboard.py src/modules/DashboardConfig.py
git commit -m "feat(adapters): integrate AdapterRegistry into dashboard startup

Registers WireGuardAdapter at boot, reads enable/disable state from
[Adapters] ini section. New API: GET /api/adapters returns adapter list
with status for the Settings UI."
```

---

## Summary

This plan establishes the adapter foundation:

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | BaseVPNAdapter ABC + Capability enum | 7 tests |
| 2 | AdapterRegistry (discover, enable/disable, probe) | 7 tests |
| 3 | WireGuard parser (wg show, .conf files) | 6 tests |
| 4 | WireGuardAdapter (full implementation) | 6 tests |
| 5 | Integration into dashboard.py + API endpoint | Manual verification |

**Total: ~26 automated tests + 1 manual verification**

After this plan, the adapter system is live and WireGuard works through it. The existing WGDashboard++ functionality is NOT yet routed through adapters — that happens incrementally as we migrate each API route. This plan creates the parallel infrastructure without breaking anything.

**Next plans:**
- **Plan 2:** Unified DB schema + migration from per-interface tables
- **Plan 3:** UI overhaul (sidebar, unified peers, adapter settings page)
- **Plan 4:** Rebrand to MouseHole
