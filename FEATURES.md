# WGDashboard++ Features

Custom features added on top of [WGDashboard v4.3.2](https://github.com/WGDashboard/WGDashboard) by Donald Zou.

## Client Peer Management

- **Client Config Access** — Admin can grant `manager` role to clients for specific WireGuard configurations
- **Client Portal Peer Management** — Clients with manager role can:
  - View peer list (active + restricted)
  - Add new peers
  - Delete peers
  - Restrict/allow peer access
  - Download peer configuration files
- **Managed Configurations View** — Dedicated client portal page listing all configurations where the client has manager access

## Gateway Management

- **Add OPNsense Gateway** — One-click workflow that creates a gateway peer with LAN subnets behind it
  - Generates ready-to-paste WireGuard configuration for reference
  - **Manual Setup panel** with field names matching the OPNsense GUI 1:1 (Peers → Add peer → Name, Public key, Allowed IPs, Endpoint address/port, Keepalive interval; Instances → Add instance → Name, Public/Private key, Listen port, Tunnel address, Peers, Disable routes)
  - Numbered step badges point to the exact OPNsense menu path
  - Per-field copy buttons
- **Add to ALL WireGuard networks** toggle — creates a separate peer with fresh keys in each WG config (duplicate-peer model for full network isolation)
- **Auto-pick Listen Port** — the next free UDP port is suggested automatically (starts at 51820) to avoid collisions between multiple OPNsense Instances on the same box. Editable inline in Peer Settings for legacy peers
- **is_gateway flag** on peers with a dedicated **Gateways** aggregation page in the sidebar — filter, per-config counters, click-to-jump to the peer's config
- **Show OPNsense Setup (manual values)** — reopen Manual Setup data for any existing gateway peer at any time
- **Mark as Gateway** toggle in Peer Settings — promote any existing peer to gateway status
- **Visual highlight** — gateway peers get a "GW" info badge and subtle left-border accent in all views (Card/List/Grid/Table/Columns)
- **Broadcast AllowedIPs** — Push a gateway peer's AllowedIPs (subnets behind it) to all other peers in the same configuration, so clients can reach servers behind OPNsense

## Network Routing

- **Routed LAN Subnets** per configuration (`Edit Configuration` → `Routed LAN Subnets`) — declare which LANs are reachable via this WG tunnel and install server-side policy routing with one **Apply Now** click. Creates `ip rule from <config_subnet> table <id>` + routes via the config's interface. Deterministic routing table id per config, idempotent. Keeps each WG network's routing independent of other tunnels sharing the same host

## Security

- **Trusted IP Addresses** — Configurable list of IPs/CIDRs that bypass TOTP verification for both admin and client logins
- **Admin Session Timeout** — Configurable session duration (5min to no limit) in Settings > Security

## UI Improvements

- **Table View** — New peer list display mode with compact table layout
  - Sortable columns: Status, Name, Traffic, Handshake
  - Status sort: online first (longest session), then offline by recency, never-connected last
  - Session duration displayed in status column
  - Full action menu via 3-dot dropdown (same as card view)
- **Collapsible Config Panel** — Configuration details (address, port, public key, traffic stats, charts) collapsed by default into a compact summary bar
- **Peer Counts in Sidebar** — Each configuration shows connected/total peer count (e.g. `8/40`)
- **Cache-Control Headers** — HTML responses prevent stale JS references after deployments

## CI/CD

- **GitLab Pipeline** — Automated testing and deployment on push
  - Test stage: 43 pytest tests covering auth, client management, config access, client portal
  - Deploy stage: git pull + full gunicorn restart + health check
  - Runs on shell executor on the production server

## License

Original WGDashboard is licensed under **Apache License 2.0**. This fork maintains the same license. See [LICENSE](LICENSE) for details.

Based on WGDashboard by [Donald Zou](https://github.com/donaldzou).
