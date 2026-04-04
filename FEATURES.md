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

## OPNsense Integration

- **Add OPNsense Gateway** — One-click button to create a gateway peer with LAN subnets behind it
  - Generates ready-to-paste WireGuard configuration
  - Generates OPNsense XML for System > Configuration > Import
  - Automatically assigns IP and configures AllowedIPs
- **Broadcast AllowedIPs** — Push a gateway peer's AllowedIPs (subnets behind it) to all other peers in the same configuration, so clients can reach servers behind OPNsense

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
