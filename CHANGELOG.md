# Changelog

All notable changes to WgDashboard++ will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a custom versioning scheme: **X.YZ** where X=major, Y=feature (+0.1), Z=bugfix (+0.01).

## [v1.7.0] - 2026-04-10

### Added
- **Path MTU monitoring** — new hourly systemd timer (`wg-pmtu-probe.service`) probes path MTU to every active WireGuard peer via kernel route cache → `tracepath` → `ping -M do` bisection → egress MTU fallback. Results are surfaced in Network Diagnostics as `configured / detected` per peer, color-coded (green when there's headroom over `interface MTU + 80 (WG overhead)`, orange when fragmentation is possible, muted when unknown).
- **On-demand PMTU re-probe button** — `↻` next to each peer's PMTU cell triggers an immediate re-probe for that single peer via `POST /api/pmtu/probe`. Fresh result lands in the UI before the next SSE snapshot.
- **On-demand MTR traces** — `⁂` button next to each peer opens a modal running `mtr --report --no-dns` against the peer's endpoint and displays the raw per-hop output with `Loss%`, `Avg`, `Wrst`, etc. Useful for diagnosing intermediate drops on the path.
- **Interface packet counters** — Network Diagnostics Interface section now shows `rx/tx packets`, `err rx/tx`, `drop rx/tx` read from `/sys/class/net/<iface>/statistics/`. Errors and drops turn orange when non-zero.
- **PMTU warnings in diagnostics** — `pmtu_below_required` warning fires when detected path MTU is below `interface MTU + 80`, propagated through the existing SSE diagnostics stream and the warnings list.
- **Fixed column widths in peer tables** — both the table view on the configuration page and the diagnostics peer table now use `table-layout: fixed` with explicit column widths, so the layout no longer jumps around when handshake text changes length.
- **Install script for bare-metal PMTU probe** — `scripts/install-pmtu-probe.sh` installs `iputils-tracepath`/`mtr-tiny`, copies the probe script, and enables the systemd timer. Idempotent.

### Improved
- **Docker image** — bundles `mtr` and `iputils` (tracepath) in the runtime stage; ships the PMTU probe script and runs it in a background loop from the entrypoint (hourly re-probe). No manual steps for Docker users.
- **Safer subprocess handling** — all new diagnostic endpoints (`/api/pmtu/probe`, `/api/diagnostics/mtr`) use `subprocess.run([...])` with list arguments and `shell=False`. No shell quoting surface, proper `FileNotFoundError` handling when `mtr`/`tracepath` is missing, proper timeouts that actually kill the child.
- **State file concurrency** — `/var/lib/wg-pmtu/state.json` writes from both the shell probe and the Python on-demand endpoint are now serialized via `flock` on a sidecar lockfile and use atomic rename. Prevents half-written JSON under load.
- **IPv6 endpoint parsing** — both the shell probe and the Python endpoint now parse `[2001:db8::1]:51820` correctly via bracket-aware regex, fixing an edge case that previously sent garbage to `ip route get`.

### Fixed
- **Datetime deprecation warning** — replaced `datetime.utcnow()` with `datetime.now(timezone.utc)` for Python 3.12+ compatibility.
- **MTR target validation** — target must now be a valid IP address (`ipaddress.ip_address()`), rejecting hostnames and arbitrary strings that previously leaked through a permissive regex.
- **Peer diagnostics interface restricted** — `/api/pmtu/probe` only accepts interfaces known to `WireguardConfigurations` (can no longer be used to probe arbitrary hosts via an unknown interface name).

## [v1.6.1] - 2026-04-10

### Added
- **Centralized Interface MTU setting** — new field in Settings → WireGuard Configuration Settings for the default MTU applied to new configurations. Does not override existing ones
- **Per-network MTU** — MTU field in each network's Configuration Settings (populated from the `[Interface]` section)
- **MTU display on network cards** — each configuration in the home list now shows its interface MTU badge
- **Routes behind server peers** — `Allowed IPs` can include extra CIDRs outside the tunnel subnet (e.g. the server's own LAN IP). The downloaded client config only includes tunnel IPs in `[Interface] Address`; extra CIDRs stay in the server-side `[Peer] AllowedIPs` so clients can reach them through the tunnel
- **Auto-start new configurations** — newly created WireGuard configurations are started and added to the autostart list automatically. No more "why isn't my tunnel working" after create

### Improved
- **MTU priority for downloaded peer configs** — now `OverridePeerSettings.MTU` → network `[Interface]` MTU → legacy per-peer MTU. Setting the network MTU propagates to all client downloads without per-peer editing
- **`_syncGatewaySubnetsToConfig` for Server peers** — routes behind a server peer (CIDRs in `allowed_ip` outside the interface subnet) are now included in `EndpointAllowedIPs` so other clients in the network can reach them
- **Create-peer validation** — CIDRs outside the tunnel subnet are accepted as routes behind the peer; at least one tunnel IP is still required
- **`is_gateway=2` (Server) preserved** — peer type was being collapsed from Server (2) to Gateway (1) during creation because of a truthy check

### Fixed
- **Cannot toggle interfaces on/off when routes overlap** — `wg-quick up` fails fatally if any `AllowedIPs` route already exists on another interface (`RTNETLINK answers: File exists`). Replaced with a manual bring-up that adds routes gracefully and skips duplicates. `wg-quick down` is unchanged
- **`wg setconf` parse error on config files with loose permissions** — `wg-quick strip` emits a warning to stderr that was being mixed into stdout via `stderr=STDOUT` and corrupted the config piped to `wg setconf`. Warnings are now discarded
- **`UnboundLocalError: mode` on peer delete and add** — `_syncGatewaySubnetsToConfig` used `mode` before it was assigned, producing a 500 response that logged the user out of the dashboard
- **Client config `[Interface] Address` polluted with non-tunnel IPs** — a server peer with `Allowed IPs = 10.200.5.1/32, 10.0.50.163/32` used to generate `Address = 10.200.5.1/32, 10.0.50.163/32` in the client config, conflicting with the server's real ethernet IP. Now only CIDRs within the WG interface subnet are included
- **Default MTU hardcoded to 1320 in code** — now defaults to 1420 (WireGuard standard); users set the environment-specific value via Settings

## [v1.6.0] - 2026-04-09

### Added
- **Automatic Policy Routing Manager** — source-based routing for WireGuard interfaces that share destination networks. Per-interface routing tables (100–252) with collision resolution, auto-sync on interface toggle, gateway-peer CRUD, startup, and backup restore. Legacy rule migration cleans up old rules without a `to` clause
- **Policy Routing UI** — Settings → Policy Routing tab with read-only rules table; Route badge on gateway peers with per-peer popover showing routes
- **Policy Routing API** — `GET /api/policyRouting/status`, `GET /api/policyRouting/status/<config>`, `POST /api/applyPolicyRoutes/<config>`
- **Diagnostics** — `policy_route_missing` and `policy_route_inactive` warnings

## [v1.5.1] - 2026-04-08

### Fixed
- **BackupScheduler not starting** — scheduler thread was created in gunicorn master process but not in the worker process. Auto-backups and scheduled backups were silently not running. Now starts via `startThreads()` in `post_worker_init`
- **Migration script missing `wgdashboard_log` database** — third database needed by the dashboard was not created during migration, causing startup failure
- **Old SQLite backups not restorable on MariaDB** — added `convert_old_backups.py` to convert `.db` files to MySQL `.sql` format, preserving transfer history
- **Backup uses `mysqldump`** — global snapshots now use `mysqldump --single-transaction` instead of `sqlite3.backup()`. Full database dump/restore works natively with MariaDB

## [v1.5] - 2026-04-08

### BREAKING CHANGE: MariaDB required
Starting with v1.5, WGDashboard++ requires **MariaDB** instead of SQLite. SQLite caused server freezes due to file-level locking when multiple threads (backup, peer updates, API requests) accessed the database concurrently. MariaDB handles concurrent access natively.

**Bare-metal migration:** `cd /opt/WGDashboard/src && sudo ./migrate_to_mariadb.sh`
**Docker:** Use the new `docker-compose.yml` which includes a MariaDB container. Auto-migration runs on first startup if a SQLite database is detected.

### Added
- **MariaDB support (required)** — eliminates all SQLite locking issues. No more server freezes during backups, restores, or concurrent operations
- **Auto-migration script** — `migrate_to_mariadb.sh` for bare-metal, automatic migration in Docker entrypoint
- **Docker Compose** — `docker/docker-compose.yml` with WGDashboard + MariaDB containers, health checks, persistent volumes
- **Restore progress bar** — polling-based progress indicator showing restore stages (1-6) with animated progress bar
- **Backup content preview** — click any backup to see expandable tree: config names, peer counts, dashboard components
- **Separate restore points** — restore points displayed in collapsible section below regular backups
- **Green indicator on last restore** — green dot on backup name and calendar day of the most recent restore
- **Auto-reload after restore** — WireGuard interfaces automatically stopped/restarted, configs re-read, page reloads

### Improved
- **Non-blocking backups** — removed threading lock that caused deadlocks. All backup operations (create, restore) run without blocking the API
- **Backup size reduced 600x** — per-config backups exclude transfer/history tables (~90 KB vs ~54 MB)
- **Backup hooks in background** — auto-backup before peer/config changes runs in background thread

### Fixed
- **Server freeze on backup/restore** — SQLite file locking with concurrent threads caused complete server hang. Resolved by MariaDB migration + lock removal
- **Restore not replacing old configs** — restore now properly removes configs not in backup and replaces the full database
- **"Allow Access" button missing** — Table and Columns views now correctly show Allow/Restrict based on peer state
- **Auto-backup toggles resetting** — boolean serialization fixed (True→"true" not "True")
- **Settings overwritten on mount** — added `loaded` guard to prevent Vue watcher from saving defaults

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
