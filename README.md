# WgDashboard++

<p align="center">
  <img alt="WgDashboard++" src="https://wgdashboard-resources.tor1.cdn.digitaloceanspaces.com/Logos/Logo-2-Rounded-512x512.png" width="128">
</p>

<p align="center">
    <a href="https://github.com/polumish/wgdashboard-plus-plus/releases/latest"><img src="https://img.shields.io/github/v/release/polumish/wgdashboard-plus-plus?style=for-the-badge&color=blue"></a>
    <a href="https://github.com/polumish/wgdashboard-plus-plus/blob/main/LICENSE"><img src="https://img.shields.io/github/license/polumish/wgdashboard-plus-plus?style=for-the-badge&color=D22128"></a>
    <a href="https://github.com/polumish/wgdashboard-plus-plus/stargazers"><img src="https://img.shields.io/github/stars/polumish/wgdashboard-plus-plus?style=for-the-badge&color=yellow"></a>
    <a href="https://github.com/polumish/wgdashboard-plus-plus/issues"><img src="https://img.shields.io/github/issues/polumish/wgdashboard-plus-plus?style=for-the-badge&color=red"></a>
</p>

<p align="center">
    <img src="https://img.shields.io/badge/Python-3670A0?style=for-the-badge&logo=python&logoColor=ffffff">
    <img src="https://img.shields.io/badge/Vue.js-42b883?style=for-the-badge&logo=vuedotjs&logoColor=ffffff">
    <img src="https://img.shields.io/badge/WireGuard-88171A?style=for-the-badge&logo=wireguard&logoColor=ffffff">
    <img src="https://img.shields.io/badge/MariaDB-003545?style=for-the-badge&logo=mariadb&logoColor=ffffff">
    <img src="https://img.shields.io/badge/Self--Hosted-0B5FFF?style=for-the-badge">
</p>

<p align="center">
    <a href="https://github.com/polumish/wgdashboard-plus-plus/releases"><img src="https://img.shields.io/badge/Release_Notes-v1.6.0-brightgreen?style=for-the-badge"></a>
    <a href="https://github.com/polumish/wgdashboard-plus-plus/discussions"><img src="https://img.shields.io/badge/Discussions-welcome-purple?style=for-the-badge&logo=github"></a>
    <a href="https://git.half.net.ua/polumish/wgdashboard-plus-plus/-/issues"><img src="https://img.shields.io/badge/Bug_Reports-welcome-orange?style=for-the-badge&logo=gitlab"></a>
</p>

## About

**WgDashboard++** is a fork of [WGDashboard](https://github.com/donaldzou/WGDashboard) v4.3.2 by **[Donald Zou](https://github.com/donaldzou)**, extended with backup & restore, MariaDB support, improved admin UX, and integration with OPNsense firewalls.

All credit for the base dashboard goes to the original author. This fork focuses on operational needs for managing multiple WireGuard networks with many peers and external clients.

> **v1.5+ requires MariaDB.** SQLite is no longer supported due to file-locking issues with concurrent operations. See [Migration Guide](docs/MIGRATION.md).

## Screenshots

### Overview
WireGuard configurations list on the home page.

![Overview](docs/images/overview.png)

### Dual-Column View
Total Commander-style split view — peer list divided into two side-by-side tables.

![Columns View](docs/images/columns-view.png)

### Display Density
Gmail-style density settings — Compact / Normal / Comfortable.

![Density Settings](docs/images/density.png)

### Compact Mode
Fit more peers on screen with tight spacing.

![Compact Mode](docs/images/sidebar-compact.png)

## Changes vs Upstream

### Backup & Restore (v1.4+)
- **Global scheduled snapshots** — daily/weekly/monthly with configurable retention (GFS rotation)
- **Per-config auto-backups** — automatic backup before any peer or config change
- **Granular restore** — select individual components (configs, settings, webhooks, clients, API keys)
- **Restore points** — automatic safety backup before every restore operation
- **Calendar & Table views** — visual backup history with color-coded dots and filters
- **Backup preview** — expandable tree showing configs, peer counts, dashboard components
- **Full database dump** — `mysqldump --single-transaction` for non-blocking backups
- **Progress bar** — real-time restore progress with stage descriptions

### Database (v1.5+)
- **MariaDB required** — eliminates SQLite file-locking issues that caused server freezes
- **Auto-migration** — `migrate_to_mariadb.sh` script for bare-metal, automatic in Docker
- **Docker Compose** — `docker/docker-compose.yml` with WGDashboard + MariaDB containers

### Client Features
- **Client portal** for self-service peer management (add/delete/restrict/allow/download)
- **Client config access management** — assign manager role per WG configuration
- **Trusted IPs** — skip TOTP for admin and client from allowed networks

### Admin Features
- **OPNsense Gateway integration** — manual setup panel matching OPNsense UI 1:1, auto port assignment, multi-network support
- **Gateways aggregation view** — all gateway peers across configurations in one page
- **Routed LAN Subnets** — server-side policy routing with one-click Apply
- **Broadcast AllowedIPs** — propagate a peer's allowed IPs to all other peers
- **Peer counts in sidebar** — connected/total counts next to each configuration
- **Configurable admin session timeout**

### Network Diagnostics (v1.6.0+)
- **Live diagnostic terminal** — neon-styled real-time view of WireGuard interface health
- **SSE-powered** — Server-Sent Events push updates instantly when state changes (no polling)
- **Per-interface diagnostics** — peers, endpoints, handshakes, transfer, system routes in one panel
- **Route validation** — cross-references AllowedIPs with kernel routing table, detects mismatches
- **Automatic warnings** — offline peers (handshake > threshold), missing routes, orphan routes, inactive peers with routes
- **Configurable threshold** — `peer_handshake_threshold` in `[Server]` section (seconds, default 300 = 5 min)
- **Settings tab** — unified view of all WG interfaces in Settings → Network Diagnostics
- **Collapsible panel redesign** — replaces old stat cards and charts with compact diagnostic terminal
- **Neon visual style** — dark semi-transparent background, color-coded status indicators with subtle glow, pulsing animations
- **REST API** — programmatic access for monitoring and alerting

#### Diagnostics API

| Endpoint | Description |
|----------|-------------|
| `GET /api/diagnostics` | Full snapshot of all interfaces (peers, routes, warnings) |
| `GET /api/diagnostics?interface=wg0` | Snapshot for a single interface |
| `GET /api/diagnostics/warnings` | All warnings across all interfaces with count |
| `GET /api/sse/diagnostics` | SSE stream — live updates pushed on state change |
| `GET /api/sse/diagnostics?interface=wg0` | SSE stream for a single interface |

All endpoints require authentication (session cookie or `wg-dashboard-apikey` header). SSE endpoints also accept `?apikey=` query parameter for cross-server access.

Example:
```bash
# Get all warnings
curl -H "wg-dashboard-apikey: YOUR_KEY" http://server:10086/api/diagnostics/warnings

# Full diagnostics for one interface
curl -H "wg-dashboard-apikey: YOUR_KEY" http://server:10086/api/diagnostics?interface=Full-Halfnet
```

Warning types:
| Type | Meaning |
|------|---------|
| `peer_offline` | Peer handshake older than threshold (default 5 min) |
| `peer_inactive` | Peer has never connected |
| `missing_route` | AllowedIPs entry exists but no kernel route found |
| `orphan_route` | Kernel route exists but no matching peer AllowedIPs |
| `policy_route_missing` | Gateway peer exists but no policy routes applied |
| `policy_route_inactive` | Policy route exists but interface is down |

### Automatic Policy Routing (v1.6.0+)

Source-based (policy) routing for WireGuard interfaces. When multiple WG interfaces have gateway peers pointing to the same destination network (e.g., `10.0.50.0/24`), each interface gets its own routing table so traffic is routed based on source address — peers from each network go through their own tunnel.

#### How It Works

**Automatic behavior — no manual configuration needed:**

1. You add a gateway peer (`is_gateway=1`) to a WG interface and specify the LAN subnets behind it (AllowedIPs)
2. `PolicyRoutingManager` automatically creates:
   - A dedicated routing table (100-252) per WG interface
   - `ip rule` entries matching source subnet → destination subnet → table
   - `ip route` entries in the dedicated table pointing through the correct WG interface
3. When the interface goes UP/DOWN, rules are created/cleaned automatically
4. On Dashboard startup, all rules are rebuilt from scratch (idempotent)
5. After backup restore, rules are re-synced automatically

**Example:** Two WG interfaces both route to `10.0.50.0/24` via different OPNsense gateways:
```
Full-Halfnet (10.200.0.0/24) → 10.0.50.0/24 via table 179
Tomash       (10.200.1.0/24) → 10.0.50.0/24 via table 216
```
Traffic from `10.200.0.x` goes through `Full-Halfnet`, traffic from `10.200.1.x` goes through `Tomash`.

#### What Happens Under the Hood

For each WG interface with gateway peers, the manager runs:
```bash
# Flush old state
ip route flush table <table_id>
ip rule del from <source> to <dest> table <table_id> priority 100

# Add new rules (one per destination subnet)
ip rule add from <source_subnet> to <dest_subnet> table <table_id> priority 100
ip route add <dest_subnet> dev <interface> table <table_id>
ip route add <source_subnet> dev <interface> table <table_id>
```

#### UI

- **Badge on gateway peers** — green "Route" badge when policy route is active, grey when inactive
- **Settings → Policy Routing** — read-only table showing all policy routing rules (source, destination, device, table ID, status)
- **Network Diagnostics** — warnings for `policy_route_missing` (gateway peer without routes) and `policy_route_inactive` (routes exist but interface is down)

#### Manual Controls

| Action | How |
|--------|-----|
| View all policy rules | Settings → Policy Routing tab, or `GET /api/policyRouting/status` |
| View rules for one interface | `GET /api/policyRouting/status/<configName>` |
| Force rebuild rules | `POST /api/applyPolicyRoutes/<configName>` |
| Rules auto-apply on | Interface toggle, gateway peer add/update/delete, dashboard startup, backup restore |

#### Policy Routing API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/policyRouting/status` | GET | All policy routing rules across all interfaces |
| `/api/policyRouting/status/<configName>` | GET | Rules for a specific interface |
| `/api/applyPolicyRoutes/<configName>` | POST | Manually rebuild rules for an interface |

Response format:
```json
{
  "status": true,
  "data": [
    {
      "config_name": "Full-Halfnet",
      "table_id": 179,
      "source_subnet": "10.200.0.0/24",
      "dest_subnet": "10.0.50.0/24",
      "device": "Full-Halfnet",
      "active": true
    }
  ]
}
```

#### Technical Details

- **Table ID assignment:** deterministic SHA1 hash of config name → range 100-252, with automatic collision resolution (shift +1)
- **Thread safety:** subprocess calls run outside the lock, only state mutation is locked
- **IPv4 only:** IPv6 subnets in AllowedIPs are filtered out (ip rule cannot mix address families)
- **Legacy migration:** on first startup after upgrade from v1.5.x, old-style ip rules (without `to` clause) are automatically cleaned and replaced with new per-destination rules
- **Subprocess timeout:** all `ip` commands have a 5-second timeout to prevent hangs

### UI Improvements
- **Display density settings** — Compact / Normal / Comfortable (Gmail-style)
- **Dual-column Table view** — split peer list into two side-by-side tables (Total Commander style)
- **Zebra striping** — alternating row backgrounds on sidebar, config list, and peer tables
- **Collapsible configuration info panel** — slim info bar replaces large cards, diagnostic terminal below
- **Narrower adaptive sidebar** — width adapts to longest configuration name (180-260px)
- **Sorting** — sort peers by status, name, or traffic in table view

### Infrastructure
- **GitLab CI/CD** — automated testing and deployment on push to main
- **GitHub mirror** — automatic sync from GitLab
- **Docker** — published image on `ghcr.io/polumish/wgdashboard-plus-plus`
- **Cache-Control headers** on HTML responses

## Versioning

WgDashboard++ uses its own versioning independent of upstream:
- **X** — major (global behavior changes)
- **Y** — feature releases (+0.1)
- **Z** — bugfixes (+0.01)

Current: **v1.6.0**

## Feature Status

| Feature | Status |
|---------|--------|
| Backup & Restore (global + per-config) | Stable |
| MariaDB database | Stable (required since v1.5) |
| Client portal, trusted IPs, density, dual-column view | Stable |
| OPNsense Gateway integration | Stable |
| Gateways aggregation view | Stable |
| Routed LAN Subnets / policy routing | Stable |
| Automatic Policy Routing (source-based) | Stable (v1.6.0+) |
| Network Diagnostics (live SSE terminal) | Stable |
| Docker deployment | Stable |

## Quick Start

### Bare-metal

```bash
# 1. Clone and install
git clone https://github.com/polumish/wgdashboard-plus-plus.git /opt/WGDashboard
cd /opt/WGDashboard/src
chmod +x wgd.sh
./wgd.sh install

# 2. Migrate to MariaDB (required for v1.5+)
sudo ./migrate_to_mariadb.sh --db-password YourStrongPassword

# 3. Start
./wgd.sh start
```

### Docker

```bash
cd docker
# Edit docker-compose.yml — change passwords!
docker compose up -d
```

See [`docker/docker-compose.yml`](docker/docker-compose.yml) for configuration options.

## Migration from SQLite

If upgrading from v1.4 or earlier, see the [Migration Guide](docs/MIGRATION.md) for step-by-step instructions.

## Deployment

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for systemd service, nginx reverse proxy, and CI/CD auto-deploy setup.

## License

Apache License 2.0, same as upstream WGDashboard.

## Upstream Documentation

For installation, API reference, and base feature documentation, see the original WGDashboard README preserved as [`README_UPSTREAM.md`](README_UPSTREAM.md).

---

**Original WGDashboard:** https://github.com/donaldzou/WGDashboard
**Original Author:** [Donald Zou](https://github.com/donaldzou)
**This Fork:** https://github.com/polumish/wgdashboard-plus-plus
**Forked by:** [polumish](https://github.com/polumish)
