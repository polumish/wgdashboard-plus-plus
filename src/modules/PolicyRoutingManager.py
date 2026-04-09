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
        self._table_id_map: dict[str, int] = {}  # config_name → assigned table_id

    def init(self, configurations_fn):
        """Late-init with a callable that returns WireguardConfigurations dict."""
        self._configurations_fn = configurations_fn

    def _table_id(self, config_name: str) -> int:
        """Deterministic routing table ID 100-252, with collision resolution.

        Thread-safety note: this method reads/writes _table_id_map without
        the lock. It is safe because callers (apply_rules, sync_all) run
        sequentially within a single request or startup path. If concurrent
        access is ever needed, wrap calls in self._lock.
        """
        if config_name in self._table_id_map:
            return self._table_id_map[config_name]

        h = int(hashlib.sha1(config_name.encode()).hexdigest(), 16)
        candidate = 100 + (h % 153)
        used = set(self._table_id_map.values())

        if len(used) >= 153:
            logger.error("_table_id: all 153 table IDs exhausted, reusing %d for %s", candidate, config_name)
            self._table_id_map[config_name] = candidate
            return candidate

        while candidate in used:
            logger.warning("table_id collision: %d already used, shifting +1 for %s", candidate, config_name)
            candidate += 1
            if candidate > 252:
                candidate = 100

        self._table_id_map[config_name] = candidate
        return candidate

    def config_subnet(self, wc) -> str | None:
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
                iface = ipaddress.ip_interface(addr)
                if iface.version == 4:
                    config_net = iface.network
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
                    if net.version != 4:
                        continue
                    if config_net and net.subnet_of(config_net):
                        continue
                    subnets.append(part)
                except (ValueError, TypeError):
                    subnets.append(part)
        return subnets

    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Run a shell command, log failures."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("cmd %s timed out after 5s", " ".join(cmd))
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="timeout")
        if result.returncode != 0 and result.stderr:
            logger.debug("cmd %s stderr: %s", " ".join(cmd), result.stderr.strip())
        return result

    def _interface_is_up(self, name: str) -> bool:
        """Check if a network interface exists. WG interfaces report state UNKNOWN when up."""
        result = self._run(["ip", "link", "show", name])
        return result.returncode == 0

    def apply_rules(self, config_name: str):
        """Flush and rebuild ip rule/route entries for one WG interface."""
        if self._configurations_fn is None:
            return
        configs = self._configurations_fn()
        if config_name not in configs:
            logger.warning("apply_rules: config %s not found", config_name)
            return

        wc = configs[config_name]
        source = self.config_subnet(wc)
        if not source:
            logger.warning("apply_rules: no IPv4 subnet for %s", config_name)
            return

        table_id = self._table_id(config_name)
        dest_subnets = self._gateway_dest_subnets(wc)
        is_up = self._interface_is_up(config_name)

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

        # Always flush old state first (even if interface is down)
        self._run(["ip", "route", "flush", "table", str(table_id)])
        # Remove old ip rules — must match the exact form they were created with
        # (including "to <dest>"). Use previously stored rules if available.
        old_rules = self._rules.get(config_name, [])
        if old_rules:
            for rule in old_rules:
                self._run(["ip", "rule", "del", "from", rule.source_subnet,
                           "to", rule.dest_subnet, "table", str(rule.table_id),
                           "priority", "100"])
        # Fallback: also try without "to" in case rules were created by old code
        while True:
            res = self._run(["ip", "rule", "del", "from", source, "table", str(table_id)])
            if res.returncode != 0:
                break

        if is_up and dest_subnets:
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
        else:
            logger.info("apply_rules: %s is down, rules saved but not applied", config_name)

        # Only state mutation under the lock
        with self._lock:
            self._rules[config_name] = rules

    def remove_rules(self, config_name: str):
        """Remove all policy routing rules for a WG interface."""
        with self._lock:
            rules = self._rules.pop(config_name, [])
        if not rules:
            return
        table_id = rules[0].table_id
        source = rules[0].source_subnet
        self._run(["ip", "route", "flush", "table", str(table_id)])
        for rule in rules:
            self._run(["ip", "rule", "del", "from", rule.source_subnet,
                       "to", rule.dest_subnet, "table", str(rule.table_id),
                       "priority", "100"])
        # Fallback cleanup
        while True:
            res = self._run(["ip", "rule", "del", "from", source, "table", str(table_id),
                             "priority", "100"])
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
