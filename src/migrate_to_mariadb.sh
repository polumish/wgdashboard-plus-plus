#!/bin/bash
# ============================================================================
# WGDashboard++ — Migrate from SQLite to MariaDB
#
# Usage: sudo ./migrate_to_mariadb.sh [--db-password PASSWORD]
#
# This script:
#   1. Installs MariaDB server (if not present)
#   2. Creates database and user
#   3. Migrates all data from SQLite
#   4. Updates wg-dashboard.ini
#   5. Restarts only the dashboard (WireGuard interfaces stay UP)
#
# Safe to run multiple times — skips steps that are already done.
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Defaults
DB_NAME="wgdashboard"
DB_JOB_NAME="wgdashboard_job"
DB_USER="wgdash"
DB_PASSWORD="${1:-WgDash_$(head -c 12 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 12)}"
DB_HOST="127.0.0.1"
INI_FILE="$SCRIPT_DIR/wg-dashboard.ini"
SQLITE_DB="$SCRIPT_DIR/db/wgdashboard.db"
SQLITE_JOB_DB="$SCRIPT_DIR/db/wgdashboard_job.db"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

# Parse args
if [ "$1" = "--db-password" ] && [ -n "$2" ]; then
    DB_PASSWORD="$2"
fi

echo "============================================================================"
echo "  WGDashboard++ — SQLite to MariaDB Migration"
echo "============================================================================"
echo ""

# Check we're root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo)"
    exit 1
fi

# Check current DB type
CURRENT_TYPE=$(grep -A1 '\[Database\]' "$INI_FILE" | grep 'type' | awk -F= '{print $2}' | tr -d ' ')
if [ "$CURRENT_TYPE" = "mysql" ]; then
    echo "Already using MySQL/MariaDB. Nothing to do."
    echo "If you want to re-migrate, change type back to 'sqlite' in wg-dashboard.ini first."
    exit 0
fi

if [ ! -f "$SQLITE_DB" ]; then
    echo "ERROR: SQLite database not found at $SQLITE_DB"
    exit 1
fi

echo "Current database: SQLite ($SQLITE_DB)"
echo "Target database:  MariaDB ($DB_NAME@$DB_HOST)"
echo ""

# ── Step 1: Install MariaDB ──────────────────────────────────────────────────
echo "[1/6] Checking MariaDB installation..."
if command -v mariadb &>/dev/null; then
    echo "  ✅ MariaDB already installed: $(mariadb --version | head -1)"
else
    echo "  📦 Installing MariaDB server..."
    apt-get update -qq
    apt-get install -y -qq mariadb-server mariadb-client
    systemctl enable mariadb
    systemctl start mariadb
    echo "  ✅ MariaDB installed and started"
fi

# Ensure MariaDB is running
if ! systemctl is-active --quiet mariadb; then
    systemctl start mariadb
fi

# ── Step 2: Create database and user ─────────────────────────────────────────
echo "[2/6] Creating database and user..."
mariadb -e "
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS \`$DB_JOB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
GRANT ALL PRIVILEGES ON \`$DB_JOB_NAME\`.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
"
echo "  ✅ Database '$DB_NAME' and user '$DB_USER' ready"

# ── Step 3: Verify Python can connect ────────────────────────────────────────
echo "[3/6] Verifying Python connection..."
$VENV_PYTHON -c "
import pymysql
conn = pymysql.connect(host='$DB_HOST', user='$DB_USER', password='$DB_PASSWORD', database='$DB_NAME')
conn.close()
print('  ✅ PyMySQL connection OK')
"

# ── Step 4: Migrate data ─────────────────────────────────────────────────────
echo "[4/6] Migrating data from SQLite to MariaDB..."
$VENV_PYTHON << PYEOF
import sqlite3
import pymysql
import re
import sys

def migrate_db(sqlite_path, mysql_db):
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    dst = pymysql.connect(host='$DB_HOST', user='$DB_USER', password='$DB_PASSWORD', database=mysql_db)
    cur = dst.cursor()

    tables = [r[0] for r in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]

    for table in sorted(tables):
        cols_info = src.execute(f'PRAGMA table_info("{table}")').fetchall()
        col_defs = []
        columns = []
        for col in cols_info:
            name = col[1]
            ctype = (col[2] or 'TEXT').upper()
            columns.append(name)

            if 'INT' in ctype:
                mysql_type = 'BIGINT'
            elif 'FLOAT' in ctype or 'REAL' in ctype or 'DOUBLE' in ctype:
                mysql_type = 'DOUBLE'
            elif 'BOOL' in ctype:
                mysql_type = 'BOOLEAN'
            elif 'DATETIME' in ctype or 'TIMESTAMP' in ctype:
                mysql_type = 'DATETIME(6)'
            elif 'JSON' in ctype:
                mysql_type = 'JSON'
            elif 'TEXT' in ctype or 'CLOB' in ctype:
                mysql_type = 'LONGTEXT'
            else:
                m = re.search(r'\((\d+)\)', ctype)
                length = m.group(1) if m else '500'
                mysql_type = f'VARCHAR({length})'

            col_defs.append(f'\`{name}\` {mysql_type}')

        cur.execute(f'DROP TABLE IF EXISTS \`{table}\`')
        cur.execute(f'CREATE TABLE \`{table}\` ({", ".join(col_defs)}) ENGINE=InnoDB')

        rows = src.execute(f'SELECT * FROM "{table}"').fetchall()
        if rows:
            placeholders = ', '.join(['%s'] * len(columns))
            col_names = ', '.join([f'\`{c}\`' for c in columns])
            insert_sql = f'INSERT INTO \`{table}\` ({col_names}) VALUES ({placeholders})'
            batch_size = 5000
            for i in range(0, len(rows), batch_size):
                batch = [tuple(row) for row in rows[i:i+batch_size]]
                cur.executemany(insert_sql, batch)
            dst.commit()

        print(f'  {table}: {len(rows)} rows')

    dst.commit()
    dst.close()
    src.close()
    return len(tables)

# Main DB
n1 = migrate_db('$SQLITE_DB', '$DB_NAME')
print(f'  ✅ Main database: {n1} tables migrated')

# Job DB (if exists)
import os
if os.path.isfile('$SQLITE_JOB_DB'):
    n2 = migrate_db('$SQLITE_JOB_DB', '$DB_JOB_NAME')
    print(f'  ✅ Job database: {n2} tables migrated')
else:
    print('  ℹ️  No job database found, skipping')
PYEOF

# ── Step 5: Update wg-dashboard.ini ──────────────────────────────────────────
echo "[5/6] Updating wg-dashboard.ini..."
cp "$INI_FILE" "${INI_FILE}.pre-mariadb.bak"

# Update Database section
sed -i "s/^type = sqlite/type = mysql/" "$INI_FILE"
sed -i "/^\[Database\]/,/^\[/{s/^host = .*/host = $DB_HOST/}" "$INI_FILE"
sed -i "/^\[Database\]/,/^\[/{s/^username = .*/username = $DB_USER/}" "$INI_FILE"
sed -i "/^\[Database\]/,/^\[/{s/^password = .*/password = $DB_PASSWORD/}" "$INI_FILE"

echo "  ✅ Config updated (backup: ${INI_FILE}.pre-mariadb.bak)"

# ── Step 6: Restart dashboard only (WG interfaces stay UP) ───────────────────
echo "[6/6] Restarting dashboard (WireGuard interfaces stay running)..."
./wgd.sh restart 2>&1 | grep -E 'started|stopped|error' || true

echo ""
echo "============================================================================"
echo "  ✅ Migration complete!"
echo ""
echo "  Database:  MariaDB ($DB_NAME@$DB_HOST)"
echo "  User:      $DB_USER"
echo "  Password:  $DB_PASSWORD"
echo ""
echo "  SQLite backup: $SQLITE_DB (not deleted, can be removed manually)"
echo "  Config backup: ${INI_FILE}.pre-mariadb.bak"
echo ""
echo "  WireGuard interfaces: NOT restarted (clients unaffected)"
echo "============================================================================"
