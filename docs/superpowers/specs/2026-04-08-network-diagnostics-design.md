# Network Diagnostics — Live WireGuard Diagnostic Terminal

**Date:** 2026-04-08
**Status:** Approved

## Summary

Real-time diagnostic terminal for WireGuard interfaces — neon-styled, SSE-powered, with automatic problem detection. Two placement points: a unified view in Settings and a per-interface view replacing the current collapsible panel content.

## Placement

### 1. Settings → "Network Diagnostics" tab

New tab in Settings alongside existing WGDashboard Settings, Peers Settings, WireGuard Configuration Settings, Backup & Restore.

Shows **all WG interfaces** in a single scrollable terminal view — one section per interface. Uses a single SSE connection for all interfaces.

### 2. WG Interface → Collapsible Panel Redesign

The current collapsible panel (`peerList.vue:432-499`) contains large cards (Address, Listen Port, Public Key), stat cards (Connected Peers, Total Usage, Total Received, Total Sent), Peers Data Usage bar chart, and Real Time Received/Sent line charts.

**Remove all of that.** Replace with:

- **Slim info bar** (1 row): Address, Port, Peers count, Traffic ↓↑, Uptime, Public Key (truncated + copy button)
- **Diagnostic terminal** for this specific interface

The existing slim header bar (`peerList.vue:418-431`) with `3/5 peers | 10.200.0.0/24 | :65350 | 1.0962 GB` stays as-is — it's the toggle button.

## Data Sources

Three system commands per interface, collected by backend:

| Command | Data |
|---------|------|
| `wg show <iface>` | peers, endpoints, allowed-ips, latest-handshake, transfer |
| `ip route show dev <iface>` | system routes through this interface (destination, gateway, metric) |
| `ip address show <iface>` | state UP/DOWN, mtu, fwmark |

## Terminal Sections

### Interface
Single line: state (UP/DOWN with pulsing indicator), mtu, fwmark.

### Peers
Table with columns: PEER (name), ENDPOINT, ALLOWED IPS, HANDSHAKE, TRANSFER (↓/↑), STATUS.

Status logic:
- `online` (green, pulsing ●) — handshake < 2 minutes ago
- `offline` (red, pulsing ●) — handshake > 2 minutes ago
- `inactive` (grey, ○) — never connected (handshake = 0)

### System Routes
Table with columns: DESTINATION, GATEWAY, METRIC, PEER (matched by gateway IP to peer's AllowedIPs), STATUS.

Status logic:
- `✓ interface subnet` — route matches the interface address
- `✓ AllowedIPs match` — route destination exists in a peer's AllowedIPs
- `⚠ peer inactive` — route exists but matched peer never connected
- `⚠ peer offline` — route exists but matched peer's handshake > 2 min
- `⚠ orphan route` — route via this interface but no matching peer AllowedIPs
- `⚠ missing route` — AllowedIPs entry exists in config but no system route found

### Warnings
Aggregated list of all warnings from Peers and Routes sections. Only shown when warnings exist.

### Footer
SSE connection status (pulsing green ● when connected) + last event timestamp.

## Visual Style

**Neon terminal** aesthetic:

- **Background:** `rgba(30, 30, 35, 0.85)` — dark grey, semi-transparent with `backdrop-filter: blur(8px)`
- **Info bar background:** `rgba(255, 255, 255, 0.03)`
- **Font:** JetBrains Mono / Fira Code / system monospace, 13px base, 12px for tables
- **Separators:** `rgba(255, 255, 255, 0.04-0.06)`
- **Row hover:** `rgba(255, 255, 255, 0.03)`

Color palette with subtle neon text-shadow glow:

| Role | Color | Glow |
|------|-------|------|
| Online/success | `#50fa7b` | `0 0 4px #50fa7b66` |
| Offline/error | `#ff5555` | `0 0 4px #ff555566` |
| Addresses/networks | `#8be9fd` (cyan) | `0 0 4px #8be9fd44` |
| Upload/warnings | `#ffb86c` (orange) | `0 0 4px #ffb86c44` |
| Section headers | `#bd93f9` (purple) | `0 0 4px #bd93f966` |
| Normal text | `#e2e8f0` | `0 0 2px #e2e8f022` |
| Muted/labels | `#6b7394` | minimal |

**Pulsing animations** on status indicators:
- Green (online): 2s cycle, ease-in-out, opacity 1→0.6
- Red (offline): 1.5s cycle
- Orange (warning): 1.8s cycle

## Architecture

### Backend

**New module: `src/modules/WireguardDiagnostics.py`**

Responsibilities:
- Collect data from `wg show`, `ip route`, `ip address` for each interface
- Cross-reference AllowedIPs with system routes to detect mismatches
- Match routes to peers by gateway IP
- Detect warnings (dead peers, orphan routes, missing routes)
- Return structured JSON per interface

**New SSE endpoint in `dashboard.py`:**

`GET /api/sse/diagnostics` — all interfaces (for Settings page)
`GET /api/sse/diagnostics?interface=wg0` — single interface (for interface page)

Implementation:
- Flask generator response with `Content-Type: text/event-stream`
- Background loop: collect diagnostics every 1 second
- Compare with previous state — only push `data:` event when something changed
- Heartbeat comment (`: heartbeat`) every 15 seconds to keep connection alive
- Authenticated — same session/API key auth as other endpoints

**gunicorn.conf.py:** Increase `threads` from 2 to 4 (each SSE connection holds a thread).

### Frontend

**New shared component: `src/static/app/src/components/networkDiagnostics/NetworkDiagnostics.vue`**

Props:
- `mode`: `"all"` | `"single"`
- `interface`: string (required when mode="single")

Behavior:
- On mount: open `EventSource` to SSE endpoint
- On message: parse JSON, update reactive state
- On unmount: close EventSource
- Render terminal sections from reactive state

**New Settings sub-component: `src/static/app/src/components/settingsComponent/networkDiagnosticsSettings.vue`**

Wrapper that renders `<NetworkDiagnostics mode="all" />`.

**Router (`router.js`):** Add child route under Settings:
```
{ name: "Network Diagnostics", path: "network_diagnostics", component: networkDiagnosticsSettings.vue }
```

**Settings tabs (`settings.vue`):** Add `{ id: "network_diagnostics", title: "Network Diagnostics" }`.

**Collapsible panel (`peerList.vue`):**
- Remove lines ~437-570 (Address/Port/Key cards, stat cards, charts)
- Add slim info bar + `<NetworkDiagnostics mode="single" :interface="configurationInfo.Name" />`

### CSS

Neon styles in a dedicated CSS file or scoped within NetworkDiagnostics.vue. Reusable classes: `.neon-green`, `.neon-red`, `.neon-cyan`, `.neon-orange`, `.neon-purple`, `.neon-text`, `.neon-muted`, `.pulse-green`, `.pulse-red`, `.pulse-orange`, `.neon-row`.

## SSE Data Format

```json
{
  "interfaces": {
    "wg0": {
      "status": "up",
      "address": "10.200.0.0/24",
      "listenPort": 65350,
      "publicKey": "NR3on3WG...",
      "mtu": 1420,
      "fwmark": "0xca6c",
      "peers": [
        {
          "name": "office-gw",
          "publicKey": "abc...",
          "endpoint": "85.10.42.1:51820",
          "allowedIps": ["10.200.0.2/32", "192.168.1.0/24"],
          "latestHandshake": 1744098072,
          "transferRx": 25165824,
          "transferTx": 1073741824,
          "status": "online"
        }
      ],
      "routes": [
        {
          "destination": "192.168.1.0/24",
          "gateway": "10.200.0.2",
          "metric": 100,
          "peer": "office-gw",
          "status": "ok",
          "statusText": "AllowedIPs match"
        }
      ],
      "warnings": [
        {
          "type": "peer_offline",
          "target": "mobile-sk",
          "message": "last handshake 3m ago (threshold: 2m)"
        }
      ]
    }
  },
  "timestamp": 1744098084
}
```

## Future Considerations (out of scope)

- **WebSocket migration** — when bidirectional communication is needed (e.g., restart interface from UI)
- **Visual network topology** — diagram showing VPN server, clients, and their routing destinations
- These are planned for future versions and not part of this implementation
