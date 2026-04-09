# Policy Routing Manager — Automatic Source-Based Routing

**Date:** 2026-04-09
**Version:** WGDashboard++ v1.6
**Status:** Approved

## Problem

Multiple WG interfaces each have a gateway peer (OPNsense, `is_gateway=1`) with the same destination network behind them (e.g., 10.0.50.0/24). The Linux kernel picks one route and all traffic goes through that single tunnel regardless of source. Users from each WG network should route through their own tunnel to OPNsense.

## Solution

Automatic source-based (policy) routing. When a gateway peer is added to a WG interface, the system automatically creates `ip rule` and `ip route` entries in a dedicated routing table so that traffic from that interface's subnet goes through that interface's tunnel.

Example:
- `wg-office` (subnet 10.200.0.0/24) has gateway peer with 10.0.50.0/24 → traffic from 10.200.0.x to 10.0.50.0/24 goes through `wg-office`
- `wg-home` (subnet 10.128.69.0/24) has gateway peer with 10.0.50.0/24 → traffic from 10.128.69.x to 10.0.50.0/24 goes through `wg-home`

## Scope

- Only gateway peers (`is_gateway=1`) trigger policy routing
- Manual route addition is out of scope (future feature)

## Architecture

### PolicyRoutingManager

New module: `src/modules/PolicyRoutingManager.py`. Singleton, initialized at gunicorn worker startup (same pattern as BackupScheduler).

#### Data Model

```python
@dataclass
class PolicyRule:
    config_name: str      # wg-office
    table_id: int         # 100-252 (deterministic hash from config name)
    source_subnet: str    # 10.200.0.0/24 (WG interface subnet)
    dest_subnet: str      # 10.0.50.0/24 (network behind gateway)
    device: str           # wg-office (network interface)
    active: bool          # applied in kernel or not
```

In-memory state:
```python
self._rules: dict[str, list[PolicyRule]]  # config_name -> rules
self._lock: threading.Lock()              # thread safety (1 worker, 2 threads)
```

#### Methods

| Method | Description |
|--------|-------------|
| `sync_all()` | Startup: iterate all WG configs, find gateway peers, build and apply all rules |
| `on_gateway_changed(config_name)` | Called on gateway peer add/update/delete. Rebuilds rules for this config |
| `apply_rules(config_name)` | Flush table + create `ip rule` and `ip route` for this interface |
| `remove_rules(config_name)` | Remove all rules for this interface (on interface down) |
| `get_status()` | Return all rules (for UI — full table) |
| `get_status_for_config(config_name)` | Return rules for one config (for UI — badge) |

#### apply_rules Logic

```
1. table_id = deterministic hash of config_name (existing _policyRoutingTableId, range 100-252)
2. ip route flush table {table_id}
3. ip rule del from {source_subnet} table {table_id}  (remove old rules)
4. For each dest_subnet from gateway peers' allowed_ip:
   a. ip rule add from {source_subnet} to {dest_subnet} table {table_id} priority 100
   b. ip route add {dest_subnet} dev {config_name} table {table_id}
5. ip route add {source_subnet} dev {config_name} table {table_id}  (own subnet route)
```

Idempotent: flush + rebuild on every call.

## Integration with Existing Code

### Call Sites

| Trigger | Location | Action |
|---------|----------|--------|
| Dashboard startup | `dashboard.py`, worker thread | `PolicyRoutingManager.sync_all()` |
| Add peer with `is_gateway=1` | `addPeers()` in `dashboard.py` | `on_gateway_changed(config_name)` |
| Update peer (gateway flag or allowed_ip changed) | `updatePeer()` in `Peer.py` | `on_gateway_changed(config_name)` |
| Delete gateway peer | `deletePeers()` in `WireguardConfiguration.py` | `on_gateway_changed(config_name)` |
| `_syncGatewaySubnetsToConfig()` completes | `dashboard.py` | `on_gateway_changed(config_name)` |
| WG interface down | interface management | `remove_rules(config_name)` |
| Backup restore complete | `BackupManager.py`, after restore | `PolicyRoutingManager.sync_all()` |
| Manual trigger | `POST /api/applyPolicyRoutes/<configName>` | `apply_rules(config_name)` |

### Code Migration

| Existing Code | Action |
|---------------|--------|
| `_applyPolicyRoutesLive()` | **Remove** — logic moves to `PolicyRoutingManager.apply_rules()` |
| `_policyRoutingTableId()` | **Move** to PolicyRoutingManager as method |
| `_configSubnetForPolicy()` | **Move** to PolicyRoutingManager as method |
| `_syncGatewaySubnetsToConfig()` | **Keep** — call `on_gateway_changed()` at the end instead of `_applyPolicyRoutesLive()` |
| `POST /api/applyPolicyRoutes/<configName>` | **Keep** — delegate to PolicyRoutingManager |

### Thread Safety

`threading.Lock()` around apply/remove operations. Same pattern as BackupManager.

## API Endpoints

### `GET /api/policyRouting/status`

Returns all active policy rules across all interfaces.

```json
{
  "status": true,
  "data": [
    {
      "config_name": "wg-office",
      "table_id": 142,
      "source_subnet": "10.200.0.0/24",
      "dest_subnet": "10.0.50.0/24",
      "device": "wg-office",
      "active": true
    },
    {
      "config_name": "wg-home",
      "table_id": 187,
      "source_subnet": "10.128.69.0/24",
      "dest_subnet": "10.0.50.0/24",
      "device": "wg-home",
      "active": true
    }
  ]
}
```

### `GET /api/policyRouting/status/<configName>`

Returns policy rules for a specific interface (used by peer badge UI).

## UI

### Badge on Gateway Peer (peerRow.vue)

Shown only for peers with `is_gateway=1`:
- **Green badge** `Policy Route Active` — rule applied in kernel
- **Grey badge** `Policy Route Inactive` — rule exists but not applied (interface down or error)

Data fetched from `/api/policyRouting/status/<configName>` on config page load.

### Policy Routing Section in Configuration Settings

Read-only table in configuration settings page:

| Source | Destination | Device | Table ID | Status |
|--------|-------------|--------|----------|--------|
| 10.200.0.0/24 | 10.0.50.0/24 | wg-office | 142 | Active |

- Read-only (manual editing is a future feature)
- Refresh button to update state
- Empty state: "No policy routes. Add a gateway peer to enable automatic source-based routing."

## Edge Cases

### Gateway peer deleted
`on_gateway_changed()` rebuilds rules from scratch. If no gateway peers remain — flush table, remove ip rules.

### WG interface not running
`apply_rules()` checks if interface is up (`ip link show`). If down — stores rules in memory with `active=false`. Next `sync_all()` or manual trigger retries.

### Same dest_subnet in 3+ tunnels
Works — each tunnel gets its own `from {source} to {dest} table {N}` rule. Kernel matches by source.

### Gateway peer with multiple subnets
`allowed_ip` may contain multiple CIDRs (e.g., `10.0.50.0/24, 10.0.60.0/24`). Each gets a separate `ip rule` + `ip route`.

### Dashboard restart / crash
Rules persist in kernel until reboot — traffic continues routing correctly. Next startup `sync_all()` rebuilds idempotently.

### Table ID collision
Hash function gives range 100-252. With typically <10 interfaces, collision is unlikely. If two configs hash to the same table_id — log warning and shift one by +1.

## Network Diagnostics Integration

New warning types in existing `WireguardDiagnostics.py`:

- **`POLICY_ROUTE_MISSING`** — gateway peer exists but policy rule not applied
- **`POLICY_ROUTE_CONFLICT`** — two interfaces have the same table_id

Warnings appear in the SSE diagnostic terminal alongside existing warnings.

## Persistence

- **No database changes** — rules are derived from existing gateway peers and config subnets
- **No PostUp/PostDown modification** — Dashboard applies rules at runtime
- **Runtime only** — `ip rule` and `ip route` entries are kernel state, rebuilt on Dashboard startup via `sync_all()`

## Future Considerations

- Manual route addition via UI (not in this version)
- Support for `is_gateway=2` (server peers) if needed
