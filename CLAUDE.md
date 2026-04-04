# WGDashboard — Fork with Client Peer Management

## What is this
Fork of [WGDashboard](https://github.com/WGDashboard/WGDashboard) v4.3.2 with custom feature: **client manager role** that allows organization admins to manage peers in their assigned WireGuard configurations.

## Current state
- **Branch:** `feature/client-peer-management`
- **Backend API:** DONE (committed)
- **Client Frontend:** TODO
- **Admin Frontend:** TODO (grant/revoke config access UI)

## What was done (backend)
New module `src/modules/DashboardClientConfigAccess.py` — stores which clients have manager access to which WireGuard configurations.

New client API endpoints in `src/client.py`:
- `GET /client/api/managedConfigurations` — list configs where client is manager
- `GET /client/api/managedConfigurations/<name>/peers` — all peers in config
- `POST /client/api/managedConfigurations/<name>/addPeers` — add peer (auto-generates keys/IP)
- `POST /client/api/managedConfigurations/<name>/deletePeers` — delete peers
- `POST /client/api/managedConfigurations/<name>/restrictPeers` — block peers
- `POST /client/api/managedConfigurations/<name>/allowAccessPeers` — unblock peers
- `GET /client/api/managedConfigurations/<name>/downloadPeer?id=` — download .conf
- `GET /client/api/managedConfigurations/<name>/availableIPs` — available IPs

New admin API endpoints in `src/dashboard.py`:
- `POST /api/clients/grantConfigAccess` — grant client manager access (body: ClientID, ConfigurationName, Role)
- `POST /api/clients/revokeConfigAccess` — revoke access (body: AccessID)
- `GET /api/clients/getConfigAccess?ClientID=` — list client's config access

## What needs to be done (frontend)

### Client portal (Vue 3 app at `src/static/client/`)
Source: `src/static/client/src/`
Build: `npm run build` (output to `src/static/dist/WGDashboardClient/`)

1. **New view:** `src/static/client/src/views/managedConfig.vue`
   - Table/grid of peers with status, handshake, traffic
   - "+ Add Peer" button (form: name only, rest auto-generated)
   - Delete / Block / Unblock buttons
   - Download .conf / QR code per peer
   - Use existing Bootstrap 5 styling

2. **Modify:** `src/static/client/src/views/index.vue`
   - Add "Managed Configurations" section
   - Show cards/list of configs where client is manager
   - Link to managed config page

3. **Modify:** `src/static/client/src/stores/clientStore.js`
   - Add Pinia actions for all managed* API calls

4. **Modify:** `src/static/client/src/router/router.js`
   - Add route `/managed/:configName` → managedConfig.vue

### Admin portal (Vue 3 app at `src/static/app/`)
Source: `src/static/app/src/`

5. On the Clients page — add UI to grant/revoke configuration access per client

## Tech stack
- Backend: Python 3.10, Flask, SQLAlchemy, SQLite
- Client frontend: Vue 3, Vite, Pinia, Bootstrap 5, Axios
- Admin frontend: Vue 3, Vite (separate app)

## Development
```bash
# Client frontend dev
cd src/static/client
npm install
npm run dev    # dev server with hot reload

# Build for production
npm run build

# Admin frontend dev
cd src/static/app
npm install
npm run dev
```

## Deployment
Server: 116.203.226.32
WGDashboard installed at: /opt/WGDashboard/
GitLab: git.half.net.ua/polumish/WGDashboard

## Patched files (outside this feature)
- `src/dashboard.py` line 314: fixed TOTP KeyError (data['totp'] → data.get('totp', ''))
- `src/wg-dashboard.ini`: SMTP port 465→587 for STARTTLS
