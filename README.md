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
    <img src="https://img.shields.io/badge/Self--Hosted-0B5FFF?style=for-the-badge">
</p>

<p align="center">
    <a href="https://github.com/polumish/wgdashboard-plus-plus/releases"><img src="https://img.shields.io/badge/Release_Notes-v1.0-brightgreen?style=for-the-badge"></a>
    <a href="https://github.com/polumish/wgdashboard-plus-plus/discussions"><img src="https://img.shields.io/badge/Discussions-welcome-purple?style=for-the-badge&logo=github"></a>
    <a href="https://git.half.net.ua/polumish/wgdashboard-plus-plus/-/issues"><img src="https://img.shields.io/badge/Bug_Reports-welcome-orange?style=for-the-badge&logo=gitlab"></a>
</p>

## About

**WgDashboard++** is a fork of [WGDashboard](https://github.com/donaldzou/WGDashboard) v4.3.2 by **[Donald Zou](https://github.com/donaldzou)**, extended with additional features for client self-service peer management, improved admin UX, and integration with OPNsense firewalls.

All credit for the base dashboard goes to the original author. This fork focuses on operational needs for managing multiple WireGuard networks with many peers and external clients.

## Changes vs Upstream

### Client Features
- **Client portal** for self-service peer management (add/delete/restrict/allow/download)
- **Client config access management** — assign manager role per WG configuration
- **Trusted IPs** — skip TOTP for admin and client from allowed networks

### Admin Features
- **OPNsense Gateway generator** ⚠️ **Alpha** — export WireGuard peer config as OPNsense XML. **Not recommended for production use.** Please report any issues you encounter while testing.
- **Broadcast AllowedIPs** — propagate a peer's allowed IPs to all other peers in one click
- **Peer counts in sidebar** — connected/total counts next to each configuration
- **Configurable admin session timeout**

### UI Improvements
- **Display density settings** — Compact / Normal / Comfortable (Gmail-style)
- **Dual-column Table view** — split peer list into two side-by-side tables (Total Commander style)
- **Zebra striping** — alternating row backgrounds on sidebar, config list, and peer tables
- **Collapsible configuration info panel** — hide/show Address, Listen Port, Public Key details
- **Narrower adaptive sidebar** — width adapts to longest configuration name (180-260px)
- **Sorting** — sort peers by status, name, or traffic in table view

### Infrastructure
- **GitLab CI/CD** — automated testing (43 tests) and deployment on push to main
- **GitHub mirror** — automatic sync from GitLab
- **Cache-Control headers** on HTML responses
- **Custom versioning** — starts at `v1.0` with semantic scheme `X.YZ`

## Versioning

WgDashboard++ uses its own versioning independent of upstream:
- **X** — major (global behavior changes)
- **Y** — feature releases (+0.1)
- **Z** — bugfixes (+0.01)

Current: **v1.0**

## Feature Status

| Feature | Status |
|---------|--------|
| Client portal, trusted IPs, density, dual-column view | ✅ Stable |
| OPNsense Gateway integration | ⚠️ **Alpha** — testing only, please [report issues](https://git.half.net.ua/polumish/wgdashboard-plus-plus/-/issues) |

## Deployment

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for installation, systemd service, nginx reverse proxy, and GitLab CI/CD auto-deploy setup.

## License

Apache License 2.0, same as upstream WGDashboard.

## Upstream Documentation

For installation, API reference, and base feature documentation, see the original WGDashboard README preserved as [`README_UPSTREAM.md`](README_UPSTREAM.md).

---

**Original WGDashboard:** https://github.com/donaldzou/WGDashboard
**Original Author:** [Donald Zou](https://github.com/donaldzou)
**This Fork:** https://github.com/polumish/wgdashboard-plus-plus
**Forked by:** [polumish](https://github.com/polumish)
