# Migration Guide: SQLite to MariaDB

Starting with **v1.5**, WGDashboard++ requires **MariaDB** (or MySQL) instead of SQLite. This guide covers migration for both bare-metal and Docker deployments.

## Why MariaDB?

SQLite uses file-level locking — when one thread writes, all others wait. WGDashboard++ has multiple concurrent threads:

- Background peer data updates (every 10 seconds)
- Backup scheduler (scheduled + event-triggered backups)
- API request handling
- Restore operations

With SQLite, these threads frequently blocked each other, causing the dashboard to freeze for seconds or minutes. MariaDB handles concurrent access natively — no locking issues.

## Bare-Metal Migration

### Prerequisites

- Root/sudo access
- WGDashboard++ v1.5+ code (git pull latest)
- Internet access (to install MariaDB packages)

### Step 1: Update Code

```bash
cd /opt/WGDashboard
git pull origin main
```

### Step 2: Run Migration Script

```bash
cd /opt/WGDashboard/src
sudo ./migrate_to_mariadb.sh --db-password YourStrongPassword
```

The script automatically:

1. **Installs MariaDB** server (if not already installed)
2. **Creates database and user** (`wgdashboard`, `wgdashboard_job`, `wgdashboard_log`)
3. **Verifies Python connectivity** (PyMySQL is already in requirements.txt)
4. **Migrates all data** from SQLite — peers, transfer history, clients, webhooks, settings, everything
5. **Converts old backups** — any `.db` files in existing backups are converted to `.sql` format
6. **Updates `wg-dashboard.ini`** — switches `[Database] type` from `sqlite` to `mysql`
7. **Restarts the dashboard** — WireGuard interfaces are NOT restarted, clients stay connected

### Step 3: Verify

```bash
# Check dashboard responds
curl -s -o /dev/null -w '%{http_code}' http://localhost:10086/

# Check WireGuard interfaces still running
wg show | grep 'interface:'

# Check MariaDB has data
mariadb wgdashboard -e "SHOW TABLES" | wc -l
```

### What Gets Migrated

| Component | Migrated? |
|-----------|-----------|
| Peer data (all configs) | Yes |
| Transfer/traffic history | Yes |
| Endpoint history | Yes |
| Restricted peers | Yes |
| Deleted peers archive | Yes |
| Dashboard clients | Yes |
| Webhooks | Yes |
| Peer jobs | Yes |
| Share links | Yes |
| API keys | Yes |
| Client access assignments | Yes |
| Configuration info (metadata) | Yes |
| wg-dashboard.ini settings | Updated (type changed to mysql) |
| WireGuard .conf files | Not touched (no changes needed) |
| Existing backups | .db files converted to .sql format |

### Rollback

If something goes wrong:

```bash
# Restore the backed-up ini file
cp /opt/WGDashboard/src/wg-dashboard.ini.pre-mariadb.bak /opt/WGDashboard/src/wg-dashboard.ini

# Restart (will use SQLite again)
cd /opt/WGDashboard/src && ./wgd.sh restart
```

The original SQLite database file is preserved at `/opt/WGDashboard/src/db/wgdashboard.db`.

## Docker Migration

### New Installation (no existing data)

Use the provided `docker-compose.yml`:

```bash
cd /opt/WGDashboard/docker

# Edit docker-compose.yml — change these passwords:
#   MARIADB_ROOT_PASSWORD
#   MARIADB_PASSWORD
#   WG_DB_PASSWORD

docker compose up -d
```

This starts two containers:
- **wgdashboard** — the dashboard application
- **mariadb** — MariaDB 11 database server

### Upgrading from Existing Docker (SQLite)

If you have an existing Docker deployment using SQLite:

#### Option A: Docker Compose (recommended)

1. **Stop the old container:**
   ```bash
   docker stop wgdashboard
   ```

2. **Copy your data volume:**
   ```bash
   # Find your data volume
   docker inspect wgdashboard | grep -A5 Mounts
   
   # The /data directory contains wg-dashboard.ini and db/wgdashboard.db
   ```

3. **Use the new docker-compose.yml:**
   ```bash
   cd /opt/WGDashboard/docker
   # Edit docker-compose.yml with your passwords
   docker compose up -d
   ```

4. **Auto-migration happens on first start:**
   - The entrypoint script detects `WG_DB_TYPE=mysql` environment variable
   - If a SQLite `.db` file exists, it automatically migrates all data to MariaDB
   - After migration, the `.db` file is renamed to `.db.migrated`
   - No manual steps required

#### Option B: Manual migration inside container

```bash
# Enter the running container
docker exec -it wgdashboard bash

# Run migration
cd /opt/wgdashboard/src
./migrate_to_mariadb.sh --db-password YourPassword
```

### Docker Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WG_DB_TYPE` | Database type: `mysql` or `sqlite` | `sqlite` |
| `WG_DB_HOST` | MariaDB hostname | `127.0.0.1` |
| `WG_DB_PORT` | MariaDB port | `3306` |
| `WG_DB_USER` | Database username | - |
| `WG_DB_PASSWORD` | Database password | - |
| `username` | Dashboard admin username | - |
| `password` | Dashboard admin password | - |
| `global_dns` | Default DNS for peers | `9.9.9.9` |
| `public_ip` | Server public IP | auto-detected |
| `wgd_port` | Dashboard web port | `10086` |
| `TZ` | Timezone | `Europe/Amsterdam` |

### Docker Compose Reference

```yaml
version: "3.8"

services:
  wgdashboard:
    image: ghcr.io/polumish/wgdashboard-plus-plus:latest
    container_name: wgdashboard
    restart: unless-stopped
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    sysctls:
      - net.ipv4.ip_forward=1
      - net.ipv4.conf.all.src_valid_mark=1
    environment:
      - WG_DB_TYPE=mysql
      - WG_DB_HOST=mariadb
      - WG_DB_USER=wgdash
      - WG_DB_PASSWORD=changeme_strong_password
    ports:
      - "10086:10086"
      - "51820:51820/udp"
    volumes:
      - wg_configs:/etc/wireguard
      - wg_data:/data
    depends_on:
      mariadb:
        condition: service_healthy

  mariadb:
    image: mariadb:11
    container_name: wgdashboard-db
    restart: unless-stopped
    environment:
      - MARIADB_ROOT_PASSWORD=changeme_root_password
      - MARIADB_DATABASE=wgdashboard
      - MARIADB_USER=wgdash
      - MARIADB_PASSWORD=changeme_strong_password
    volumes:
      - mariadb_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  wg_configs:
  wg_data:
  mariadb_data:
```

## Backup & Restore After Migration

### How Backups Work with MariaDB

| Operation | Method |
|-----------|--------|
| Global snapshot (create) | `mysqldump --single-transaction` (non-blocking) |
| Global snapshot (restore) | `mysql < dump.sql` |
| Per-config backup | JSON export via SQLAlchemy (cross-database compatible) |
| Per-config restore | JSON import via SQLAlchemy |

### Old SQLite Backups

Old backups created before migration (containing `.db` files) are automatically converted to `.sql` format during migration. They remain fully restorable.

If you have backups that weren't converted, run:

```bash
cd /opt/WGDashboard/src
./venv/bin/python3 convert_old_backups.py
```

## Troubleshooting

### Dashboard won't start after migration

Check the error log:
```bash
tail -20 $(ls -t /opt/WGDashboard/src/log/error_*.log | head -1)
```

Common issues:
- **"Access denied for user"** — the migration script may have missed a database. Run:
  ```bash
  mariadb -e "GRANT ALL PRIVILEGES ON *.* TO 'wgdash'@'localhost'; FLUSH PRIVILEGES;"
  ```
- **"Can't connect to MySQL server"** — MariaDB not running:
  ```bash
  systemctl start mariadb
  ```

### WireGuard interfaces went down

The migration script does NOT touch WireGuard interfaces. If they went down, restart them:
```bash
wg-quick up wg0  # for each interface
```

Or restart the dashboard which will bring up autostart interfaces:
```bash
cd /opt/WGDashboard/src && ./wgd.sh restart
```

### Reverting to SQLite

```bash
cp /opt/WGDashboard/src/wg-dashboard.ini.pre-mariadb.bak /opt/WGDashboard/src/wg-dashboard.ini
cd /opt/WGDashboard/src && ./wgd.sh restart
```

Note: Any data changes made after migration will be lost when reverting.
