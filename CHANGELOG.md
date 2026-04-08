# Changelog

All notable changes to WgDashboard++ will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a custom versioning scheme: **X.YZ** where X=major, Y=feature (+0.1), Z=bugfix (+0.01).

## [v1.5] - 2026-04-08

### Improved
- **Non-blocking full database backup** — global snapshots now use `sqlite3.backup()` API to create an atomic copy of the entire database (including transfer history) without blocking the server. Previously, reading 177,000+ transfer rows via SELECT locked the database and froze the dashboard for minutes
- **Backup size reduced 600x for JSON export** — per-config and granular restore data excludes transfer/history tables (reduced from ~54 MB to ~90 KB). Full database is still preserved as a binary `.db` file in each snapshot
- **Backup hooks run in background thread** — auto-backup before peer/config changes no longer blocks the API response. The dashboard remains responsive during backup creation
- **Targeted DB export for per-config backups** — only reads tables belonging to that specific configuration instead of scanning the entire database

### Fixed
- **Server freeze when adding peers** — the backup hook was synchronously exporting all 38 database tables (including 177k transfer rows) inside the API request handler, blocking the single gunicorn worker. Now runs in a background thread with targeted table export
- **"Allow Access" button missing in Table and Columns views** — restricted peers showed "Restrict Access" instead of "Allow Access" in the action dropdown. Card/Grid/List views were not affected
- **Auto-backup toggles resetting to off** — `str(True)` produced "True" (capital T) but configparser only recognizes "true" (lowercase), causing settings to silently revert after save
- **Settings overwritten on page load** — Vue watcher fired immediately on mount, sending default values back to server before actual settings were loaded

## [v1.4] - 2026-04-06

### Added
- **Backup & Restore** — complete two-level backup system:
  - **Global Snapshots** (Settings → Backup & Restore) — full dashboard backup including all WireGuard configs, peer data, dashboard settings, webhooks, peer jobs, share links, client portal, and API keys
  - **Scheduled backups** — configurable daily/weekly/monthly with independent toggles, time/day selectors, and per-type retention limits (GFS rotation scheme)
  - **Per-config auto-backups** — automatic backup before any peer or config change (add/delete/restrict/allow peer, update peer settings, change interface config, edit RoutedLAN/NetworkMode). Cooldown prevents duplicates during bulk operations
  - **Granular restore** — select individual components to restore (configurations, settings, webhooks, peer jobs, share links, client portal, API keys) via checkbox tree in restore modal
  - **Restore points** — automatic backup of current state created before every restore operation, providing an undo safety net
  - **Calendar view** — month-based calendar with color-coded dots (green=daily, yellow=weekly, cyan=monthly, gray=manual, orange=auto). Click any day to see that day's backups
  - **Table view** — compact sortable list with filter pills (All/Daily/Weekly/Monthly/Auto)
  - **Per-config backup panel** — accessible via "Backups" button in configuration action bar (after Active Jobs), shows auto-triggered and global backups for that specific config
  - **Storage management** — configurable max storage size, visual progress bar, backup path configuration
  - **Integrity verification** — SHA-256 checksums for every file in backup, verified before any restore
  - **JSON backup format** — database-agnostic (works across SQLite/PostgreSQL/MySQL), structured directories with manifest.json
  - **Legacy migration** — existing WGDashboard_Backup/ files automatically converted to new format on first startup
  - **Download** — backups downloadable as .tar.gz archives
  - **Density support** — all backup UI respects Compact/Normal/Comfortable display density setting

### Changed
- Old per-config backup UI removed from Configuration Settings (replaced by new system)

### Fixed
- `deleteBackup()` previously only deleted .conf file, leaving orphaned .sql files

## [v1.3] - 2026-04-06

### Added
- **Auto-suggest Address and ListenPort** when creating a new WG configuration — scans existing configs, proposes next free /24 in 10.200.0.0/16 and next free port. Fields remain editable.
- **Auto-sync gateway subnets** — when an OPNsense Gateway is added, its LAN subnets are automatically propagated to Override EndpointAllowedIPs (client-side routing) and Routed LAN Subnets (server-side policy routing), then policy routing is applied immediately. Works with multiple gateways per config (union of all gateway LANs). Also triggers on: gateway flag toggle, peer settings update, peer deletion.

### Fixed
- **Adding peers to stopped configurations** — previously failed with shell error "No such device". Now peers are saved to DB and appended to .conf file; `wg-quick up` picks them up automatically when the configuration is started.

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

[v1.3]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.3
[v1.2]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.2
[v1.1]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.1
[v1.02]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.02
[v1.01]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.01
[v1.0]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.0
