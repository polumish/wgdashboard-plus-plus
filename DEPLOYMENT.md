# Deployment Guide

This guide describes how WgDashboard++ is deployed in our environment (Hetzner bare metal, Debian/Ubuntu, Python venv + gunicorn).

## Prerequisites

- Debian 11+ / Ubuntu 22.04+ with root access
- WireGuard installed (`wg-quick`, `/etc/wireguard/` directory)
- Python 3.10+ and `python3-venv`
- Git
- GitLab Runner (optional, for CI/CD auto-deploy)

## Initial Installation

```bash
# Clone the repo
cd /opt
git clone https://github.com/polumish/wgdashboard-plus-plus.git WGDashboard
cd WGDashboard/src

# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# Start manually to verify
./wgd.sh start
```

Panel listens on `0.0.0.0:10086` by default. Change in `wg-dashboard.ini` after first start.

## First Login

Default credentials:
- **Username:** `admin`
- **Password:** `admin`

⚠️ **Change the password immediately** after first login via Settings → Account.

## Systemd Service

Create `/etc/systemd/system/wg-dashboard.service`:

```ini
[Unit]
After=syslog.target network-online.target
Wants=wg-quick.target
ConditionPathIsDirectory=/etc/wireguard

[Service]
Type=forking
PIDFile=/opt/WGDashboard/src/gunicorn.pid
WorkingDirectory=/opt/WGDashboard/src
ExecStart=/opt/WGDashboard/src/wgd.sh start
ExecStop=/opt/WGDashboard/src/wgd.sh stop
ExecReload=/opt/WGDashboard/src/wgd.sh restart
TimeoutSec=120
PrivateTmp=yes
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
systemctl daemon-reload
systemctl enable --now wg-dashboard
```

## Reverse Proxy (optional)

If exposing publicly, put behind nginx/caddy with TLS. Minimal nginx example:

```nginx
server {
    listen 443 ssl http2;
    server_name dashboard.example.com;

    ssl_certificate     /etc/letsencrypt/live/dashboard.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dashboard.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:10086;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Configuration

Main config: `/opt/WGDashboard/src/wg-dashboard.ini`

Key `Server` section values for WgDashboard++ fork:
- `dashboard_density` — `compact` / `normal` / `comfortable`
- `dashboard_peer_list_display` — `table` / `columns` / `grid` / `list`
- `gitlab_api_token` — PAT for update checks (optional)
- `gitlab_project_url` — e.g. `https://git.half.net.ua/api/v4/projects/49`

Restart after manual edits:
```bash
systemctl restart wg-dashboard
```

## CI/CD Auto-Deploy (GitLab)

Our setup uses GitLab Runner on the same host with tag `wgdashboard`.

### Runner setup
```bash
# Install gitlab-runner
curl -L "https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh" | bash
apt install gitlab-runner

# Register with tag "wgdashboard", executor "shell"
gitlab-runner register
```

### Required CI/CD variables (in GitLab project settings)
- `GH_MIRROR_TOKEN` — GitHub PAT with `repo` + `workflow` scopes (masked, unprotected)

### Pipeline stages
1. **test** — runs pytest on all commits
2. **deploy** — on `main` branch: fetches, merges, installs deps, restarts gunicorn, health-check
3. **mirror** — pushes `main` to GitHub (`polumish/wgdashboard-plus-plus`)

See [`.gitlab-ci.yml`](.gitlab-ci.yml) for the full pipeline definition.

## Health Check

```bash
curl -sf http://localhost:10086/api/getDashboardTheme
```

Returns `200 OK` with JSON if gunicorn is up.

## Logs

- Access log: `/opt/WGDashboard/src/log/access_YYYY_MM_DD_HH_MM_SS.log`
- Error log: `/opt/WGDashboard/src/log/error_YYYY_MM_DD_HH_MM_SS.log`
- Systemd: `journalctl -u wg-dashboard -f`

## Upgrading

Via CI/CD: push to `main` → auto-deploy.

Manual:
```bash
cd /opt/WGDashboard
git pull
cd src
source venv/bin/activate
pip install -r requirements.txt
./wgd.sh restart
```

## Backup

Critical files to back up:
- `/opt/WGDashboard/src/wg-dashboard.ini` — configuration
- `/opt/WGDashboard/src/db/` — SQLite databases (sessions, jobs, logs)
- `/etc/wireguard/` — WireGuard configs (managed by `wg-quick`)
