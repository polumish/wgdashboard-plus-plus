# Changelog

All notable changes to WgDashboard++ will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a custom versioning scheme: **X.YZ** where X=major, Y=feature (+0.1), Z=bugfix (+0.01).

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

[v1.01]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.01
[v1.0]: https://github.com/polumish/wgdashboard-plus-plus/releases/tag/v1.0
