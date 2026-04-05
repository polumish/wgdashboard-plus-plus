# Changelog

All notable changes to WgDashboard++ will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a custom versioning scheme: **X.YZ** where X=major, Y=feature (+0.1), Z=bugfix (+0.01).

## [v1.2] - 2026-04-05

### Added
- **Routed LAN Subnets** per configuration (`Edit Configuration` → new section) — declare which LANs are reachable via a WG tunnel and apply server-side policy routing with one click. Installs `ip rule from <config_subnet> table <id>` + routes via the config's interface. Deterministic table id (100-252) derived from config name, idempotent Apply
- Auto-pick next free **OPNsense Listen Port** when creating a gateway peer (starts at 51820, scans all gateway peers across configs)
- **Inline edit** of OPNsense Listen Port for existing gateway peers (pencil icon in Show OPNsense Setup panel)
- **Show OPNsense Setup (manual values)** button in Peer Settings — retrieve Manual Setup values for any existing gateway peer (not only at creation time)
- Manual Setup field names now match the OPNsense GUI **1:1** (Enabled, Name, Public key, Pre-shared key, Allowed IPs, Endpoint address, Endpoint port, Instances, Keepalive interval / Private key, Listen port, Tunnel address, Peers, Disable routes) with numbered step badges pointing to `VPN → WireGuard → Peers` then `Instances`

### Fixed
- **Portal logout bug when peer id contained `/`** — WireGuard public keys are base64 with `/`, `+`, `=`. The GET endpoint for "Show OPNsense Setup" had `<peerId>` in its path and Flask's route converter rejected the slash → 404 → frontend redirected to signin. Switched to POST with `{id}` in JSON body
- **Portal logout bug on opening orphaned configs** — deleted configurations left partial state behind (orphan `ConfigurationsInfo` row + `_history_endpoint` table). Opening such a config crashed `getRestrictedPeers()` with `sqlite3.OperationalError: no such table` → HTTP 500 → frontend interpreted as session loss → logout. Fixed `deleteConfiguration()` to drop all per-config tables (including `_history_endpoint`) independently with `DROP TABLE IF EXISTS` and to remove the `ConfigurationsInfo` row. Added defensive `OperationalError` handling in `getPeers()` / `getRestrictedPeers()` so any future orphan just shows an empty list

## [v1.1] - 2026-04-05

### Added
- **Gateways** aggregation view (new sidebar entry) — lists all gateway peers across every WireGuard configuration with filter, per-config counters, and click-to-jump to the peer's configuration
- `is_gateway` flag on peers (with idempotent schema migration for existing DBs)
- **"Add to ALL WireGuard networks"** toggle in OPNsense Gateway modal — creates a separate peer with fresh keys in each WG config (duplicate-peer model: full isolation, no cross-tunnel routing)
- Multi-network result UI: per-network selector with Manual Setup + `.conf` tabs
- Visual highlight for gateway peers: info-coloured "GW" badge and subtle left-border accent in Card, List, Grid, Table, and Columns views
- New APIs: `GET /api/getAllGateways`, `POST /api/setPeerGatewayFlag/<configName>`

## [v1.02] - 2026-04-05

### Fixed
- Restored full three-dots action menu in Columns peer-list view (was showing only 4 items — Settings, Schedule Jobs, Restrict, Delete — missing Download/QR/Config/Share/Assign/Broadcast)
- Removed dangerous OPNsense XML export: the generated file had `<opnsense>` as root and overwrote the entire OPNsense `config.xml` when imported via System → Configuration → Restore. Replaced with a "Manual Setup" panel with copyable fields and a standard wg-quick `.conf` importable via VPN → WireGuard → Instances → Import (OPNsense 23.7+)
- `AllowedIPs` in the generated OPNsense config now correctly uses the WG tunnel network (e.g. `10.200.0.0/24`) instead of the server's own address

## [v1.01] - 2026-04-05

### Added
- Docker deployment support with published image on `ghcr.io/polumish/wgdashboard-plus-plus`
- CI stage to automatically build and publish Docker images on version tags
- Documented Docker deployment in DEPLOYMENT.md

## [v1.0] - 2026-04-04

Initial release of WgDashboard++, forked from [WGDashboard v4.3.2](https://github.com/donaldzou/WGDashboard) by Donald Zou.

### Added
#### UI Improvements
- Display density settings (Compact / Normal / Comfortable) — Gmail-style
- Dual-column Table view — split peer list into two side-by-side tables
- Zebra striping on sidebar, config list, and peer tables
- Collapsible configuration info panel
- Adaptive sidebar width (180-260px) based on config names
- Peer counts in sidebar (connected/total)
- Sortable peer table (status, name, traffic)
- Rebranded to WgDashboard++ with solid dark header

#### Client Features
- Client portal for self-service peer management
- Client config access management (manager role per WG config)
- Trusted IPs — skip TOTP from allowed networks

#### Admin Features
- Broadcast AllowedIPs to all peers
- Configurable admin session timeout
- OPNsense Gateway generator (alpha)

#### Infrastructure
- GitLab CI/CD with 43 tests and auto-deploy
- GitHub mirror sync
- Upstream watch — daily GitLab issues for upstream releases/commits
- Cache-Control headers on HTML responses

[v1.2]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.2
[v1.1]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.1
[v1.02]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.02
[v1.01]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.01
[v1.0]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.0
