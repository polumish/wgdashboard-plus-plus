# MouseHole — Universal VPN Management Panel

**Date:** 2026-04-08
**Status:** Approved
**Approach:** Incremental Extraction (B) — refactor WGDashboard++ into modular architecture, add adapters one by one

## Overview

MouseHole is a universal VPN management panel built on top of WGDashboard++. WireGuard becomes one of several VPN adapters in a plugin-based architecture. Each adapter declares its capabilities and the UI adapts dynamically.

**MVP protocols:** WireGuard (+ AmneziaWG) / OpenVPN / ZeroTier

**Target audience:** MSP/sysadmins managing 5-50 clients with mixed VPN setups, growing toward open-source community and eventually SaaS.

## 1. Adapter Interface

Each VPN protocol implements a class inheriting from `BaseVPNAdapter`.

### Required methods (every adapter MUST implement)

| Method | Returns | Purpose |
|--------|---------|---------|
| `get_status()` | up / down / error | Overall service health |
| `start()` | bool | Start the VPN service |
| `stop()` | bool | Stop the VPN service |
| `list_interfaces()` | list of dicts | Name, port, subnet, peer count per interface |
| `get_interface(name)` | dict | Detailed interface info |

### Capabilities (optional, adapter declares what it supports)

| Capability | Methods | WG | OpenVPN | ZeroTier |
|------------|---------|:--:|:-------:|:--------:|
| PEER_MANAGEMENT | add/remove/list/get_peer | Y | Y | Y |
| TRAFFIC_STATS | get_transfer_data, get_endpoint_data | Y | Y | limited |
| CONFIG_GENERATION | generate_client_config, generate_qr | Y | Y | N |
| KEY_MANAGEMENT | generate_keys, rotate_keys | Y | N | N |
| ACCESS_CONTROL | restrict_peer, unrestrict_peer | Y | Y | Y (authorize/deauthorize) |

### Plugin architecture

Adapters are **standalone plugins**, not hardcoded into the core. MouseHole core ships with zero VPN adapters — each protocol is installed separately.

**Distribution:**
- `mousehole-core` — the dashboard, UI, routing engine, backup system. No VPN code.
- `mousehole-wireguard` — WireGuard + AmneziaWG adapter
- `mousehole-openvpn` — OpenVPN adapter + built-in CA
- `mousehole-zerotier` — ZeroTier adapter

**Installation methods:**
- `pip install mousehole-wireguard` (when published to PyPI)
- Copy adapter directory into `src/adapters/` (manual / git clone)
- Docker: separate images per combo (`mousehole-wg`, `mousehole-full`) or mount adapter dirs as volumes

**Each adapter directory is self-contained:**
```
src/adapters/
    base.py                 # BaseVPNAdapter, Capability enum (part of core)
    registry.py             # discover, enable/disable adapters (part of core)
    wireguard/              # mousehole-wireguard plugin
        __init__.py         # WireGuardAdapter(BaseVPNAdapter)
        parser.py           # wg show parsing, .conf file handling
        manifest.json       # {"name": "WireGuard", "version": "1.0", "author": "..."}
    openvpn/                # mousehole-openvpn plugin
        __init__.py         # OpenVPNAdapter(BaseVPNAdapter)
        management.py       # OpenVPN management interface (TCP socket)
        pki.py              # minimal CA: generate/revoke certs, CRL
        manifest.json
    zerotier/               # mousehole-zerotier plugin
        __init__.py         # ZeroTierAdapter(BaseVPNAdapter)
        api_client.py       # ZeroTier local API wrapper (localhost:9993)
        manifest.json
```

### Registration flow

1. At startup, MouseHole scans `src/adapters/` for directories containing `manifest.json`
2. Checks `wg-dashboard.ini` section `[Adapters]` for enabled/disabled state
3. For each enabled adapter: loads the module, calls `probe()` to check if the VPN service is available on this system
4. Adapter registers itself with its list of capabilities
5. UI queries the registry to determine which actions to show per interface

### Adapter management in UI

Settings → Adapters page:
- List of discovered adapters (installed on disk) with name, version, author from manifest
- Toggle switch to enable/disable each adapter (persisted to ini)
- Status indicator: installed / enabled / active (VPN service detected) / error
- Disabled adapters are completely invisible in the rest of the UI

### ini config example

```ini
[Adapters]
wireguard = enabled
openvpn = enabled
zerotier = disabled
```

A user who only needs WireGuard installs only the WG plugin and gets a clean, lightweight dashboard with no OpenVPN/ZeroTier clutter.

## 2. Data Model

Unified schema replacing WGDashboard++'s per-interface tables.

### Tables

```sql
vpn_interfaces (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    adapter_type    VARCHAR(50) NOT NULL,   -- 'wireguard', 'openvpn', 'zerotier'
    name            VARCHAR(100) NOT NULL,
    listen_port     INT,
    subnet          VARCHAR(50),
    status          VARCHAR(20) DEFAULT 'unknown',
    config_path     VARCHAR(500),
    extra_json      JSON,                   -- protocol-specific fields
    created_at      DATETIME,
    updated_at      DATETIME,
    UNIQUE(adapter_type, name)
)

peers (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    interface_id    INT NOT NULL REFERENCES vpn_interfaces(id),
    identifier      VARCHAR(255) NOT NULL,  -- public key (WG), CN (OVPN), member ID (ZT)
    name            VARCHAR(255),
    allowed_ips     TEXT,
    endpoint        VARCHAR(255),
    enabled         BOOLEAN DEFAULT TRUE,
    extra_json      JSON,
    created_at      DATETIME,
    updated_at      DATETIME
)

peer_traffic (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    peer_id         INT NOT NULL REFERENCES peers(id),
    timestamp       DATETIME NOT NULL,
    rx_bytes        BIGINT DEFAULT 0,
    tx_bytes        BIGINT DEFAULT 0,
    INDEX(peer_id, timestamp)
)

peer_endpoints (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    peer_id         INT NOT NULL REFERENCES peers(id),
    timestamp       DATETIME NOT NULL,
    endpoint_ip     VARCHAR(255),
    INDEX(peer_id, timestamp)
)

network_groups (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    name            VARCHAR(100) NOT NULL UNIQUE,
    description     TEXT
)

network_group_members (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    group_id        INT NOT NULL REFERENCES network_groups(id),
    peer_id         INT NOT NULL REFERENCES peers(id),
    UNIQUE(group_id, peer_id)
)

routing_rules (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    name            VARCHAR(255),
    rule_type       ENUM('auto', 'manual') NOT NULL,
    source_type     ENUM('group', 'interface') NOT NULL,
    source_id       INT NOT NULL,
    dest_type       ENUM('group', 'interface') NOT NULL,
    dest_id         INT NOT NULL,
    allowed_subnets TEXT,                   -- NULL = all
    allowed_ports   TEXT,                   -- NULL = all, e.g. "22,3306,5432"
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      DATETIME
)
```

### `extra_json` examples

**WireGuard peer:** `{"preshared_key": "...", "persistent_keepalive": 25}`
**OpenVPN client:** `{"common_name": "ivan-laptop", "cipher": "AES-256-GCM", "cert_expiry": "2027-01-01"}`
**ZeroTier member:** `{"network_id": "abc123", "managed_ips": ["10.147.20.5"], "authorized": true}`

### Migration

Automated script converts WGDashboard++ per-interface tables into the unified schema. Same approach as the SQLite-to-MariaDB migration.

## 3. Cross-VPN Routing

Two mechanisms: automatic via Network Groups, manual via Routing Rules.

### Network Groups (automatic)

Admin creates a group (e.g., "Kyiv Office"), adds peers from different VPNs. MouseHole automatically:

1. Determines each peer's subnets from `allowed_ips` / managed routes
2. Generates `iptables` FORWARD rules between group members across VPN interfaces
3. Adds routes via `ip route` / `ip rule` for policy routing
4. Regenerates rules on any group membership change

### Manual Rules

For fine-grained control:

```
Source: OpenVPN/office-vpn (all peers)
Destination: WireGuard/nm-bella (subnet 10.94.179.0/24)
Allowed ports: 3306, 5432, 22
Action: ACCEPT
```

### OS-level implementation

- `iptables` FORWARD chain for filtering
- `ip route` / `ip rule` for policy routing between VPN interfaces
- Rules stored in DB + applied at startup and on config changes
- Safety: auto-rollback after 60 seconds if a rule breaks connectivity (similar to `iptables-apply`)
- Dedicated iptables chain `MOUSEHOLE-FORWARD` to avoid conflicts with other rules

### UI

"Routing" tab: table of active rules, source/destination visualization, "Test connectivity" button (ping/traceroute between peers).

## 4. UI Design

### Status Bar (always visible, top)
Compact strip: total VPN interfaces count, overall status (all up / N down), active peers count, aggregate throughput.

### Main View — Topology Map
Interactive network diagram (D3.js or Cytoscape.js):
- Central node: MouseHole server
- Around it: VPN interfaces, color-coded by type (WG blue, OpenVPN green, ZeroTier purple)
- From each interface: peers as smaller nodes
- Network Groups shown as dashed outlines
- Cross-VPN routes as lines between groups
- Click peer: side panel with details, traffic graph, actions

### Sidebar Navigation

| Icon | Label | Content |
|------|-------|---------|
| Home | Dashboard | Topology map + status |
| Radio | Interfaces | All VPN interfaces, tabs by type |
| Users | Peers | Unified peer list with filters |
| Link | Network Groups | Groups + cross-VPN routing config |
| Route | Routing Rules | Manual rules table |
| Save | Backups | Existing backup/restore system |
| Gear | Settings | Adapters, general config |

### Interface View
Preserves current WGDashboard++ UX: peer list, traffic, actions. Adapts to adapter capabilities — missing capabilities hide corresponding UI elements.

### Unified Peers View
All peers from all VPNs in one table. Columns: name, VPN type (badge), interface, IP, status (online/offline), last seen, traffic. Filters by VPN type, group, status. Search by name/IP.

## 5. MVP Adapter Details

### WireGuard (refactor existing code)
- **Capabilities:** all (PEER_MANAGEMENT, TRAFFIC_STATS, CONFIG_GENERATION, KEY_MANAGEMENT, ACCESS_CONTROL)
- **Data source:** `wg show`, `.conf` files
- **AmneziaWG:** same interface, detected by binary name
- **Migration:** existing WGDashboard++ code moves into `adapters/wireguard/`

### OpenVPN
- **Capabilities:** PEER_MANAGEMENT, TRAFFIC_STATS, CONFIG_GENERATION, ACCESS_CONTROL
- **Data source:** Management Interface (TCP socket, default port 7505)
- **Config:** parse `server.conf`, generate `.ovpn` client profiles with embedded certs
- **PKI:** minimal built-in CA using pyOpenSSL — generate cert, revoke, update CRL. No EasyRSA dependency.
- **No KEY_MANAGEMENT** (PKI model, not key-pair model)

### ZeroTier
- **Capabilities:** PEER_MANAGEMENT, TRAFFIC_STATS (limited)
- **Data source:** ZeroTier Local Service API (`http://localhost:9993`, reads authtoken from `/var/lib/zerotier-one/authtoken.secret`)
- **Peers = members:** authorize/deauthorize via API
- **No CONFIG_GENERATION** (clients join by network ID)
- **No KEY_MANAGEMENT** (ZT manages keys internally)

## 6. Roadmap

| Version | Milestone | Key deliverables |
|---------|-----------|-----------------|
| v2.0 | MouseHole Foundation | Rebrand, adapter interface, WG adapter extraction, unified DB schema, new sidebar + unified peers view |
| v2.1 | OpenVPN | OpenVPN adapter, minimal CA, `.ovpn` generation, OpenVPN peers in unified view |
| v2.2 | ZeroTier | ZeroTier adapter, member management, three-protocol validation |
| v2.3 | Cross-VPN Routing | Network Groups, manual routing rules, iptables/ip route generation, rollback safety |
| v2.4 | Topology Dashboard | Interactive network map (D3.js/Cytoscape.js), status bar, traffic drill-down |
| v2.5+ | Growth | More adapters (Tailscale, IPsec, Outline), multi-server, remote backups, SaaS multi-tenant |

Each version is a working release. Users can adopt at any point.

## 7. Technical Decisions

- **Database:** MariaDB (already migrated from SQLite in v1.5)
- **Backend:** Python/Flask + Gunicorn (existing stack)
- **Frontend:** Vue.js (existing stack)
- **Topology visualization:** D3.js or Cytoscape.js (evaluate during v2.4)
- **OpenVPN PKI:** pyOpenSSL (no external EasyRSA dependency)
- **ZeroTier API:** requests library, authtoken from filesystem
- **Routing:** iptables + ip route/ip rule, managed via subprocess calls
- **Config format:** `wg-dashboard.ini` extended with adapter-specific sections
