#!/usr/bin/env python3
"""Auto-migrate WGDashboard data from SQLite to MySQL/MariaDB.

Reads connection details from wg-dashboard.ini [Database] section.
Migrates all tables from SQLite .db files to the configured MySQL database.
Safe to run multiple times — drops and recreates tables.

Used by:
  - docker/entrypoint.sh (automatic migration on container start)
  - src/migrate_to_mariadb.sh (bare-metal migration script)
"""

import configparser
import os
import re
import sqlite3
import sys


def get_mysql_connection(ini_path="wg-dashboard.ini"):
    """Read MySQL credentials from ini and return a pymysql connection."""
    import pymysql

    parser = configparser.ConfigParser(strict=False)
    parser.read(ini_path)

    host = parser.get("Database", "host", fallback="127.0.0.1")
    port = int(parser.get("Database", "port", fallback="3306") or 3306)
    user = parser.get("Database", "username", fallback="wgdash")
    password = parser.get("Database", "password", fallback="")

    return pymysql.connect(host=host, port=port, user=user, password=password), user


def migrate_db(sqlite_path, mysql_db_name, mysql_conn_factory):
    """Migrate one SQLite database to a MySQL database."""
    import pymysql

    if not os.path.isfile(sqlite_path):
        print(f"  Skipping {sqlite_path} — file not found")
        return 0

    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row

    conn, user = mysql_conn_factory()
    cur = conn.cursor()

    # Ensure database exists
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{mysql_db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute(f"GRANT ALL PRIVILEGES ON `{mysql_db_name}`.* TO '{user}'@'%%'")
    cur.execute("FLUSH PRIVILEGES")
    cur.execute(f"USE `{mysql_db_name}`")

    tables = [r[0] for r in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]

    for table in sorted(tables):
        cols_info = src.execute(f'PRAGMA table_info("{table}")').fetchall()

        col_defs = []
        columns = []
        for col in cols_info:
            name = col[1]
            ctype = (col[2] or "TEXT").upper()
            columns.append(name)

            if "INT" in ctype:
                mysql_type = "BIGINT"
            elif any(t in ctype for t in ("FLOAT", "REAL", "DOUBLE")):
                mysql_type = "DOUBLE"
            elif "BOOL" in ctype:
                mysql_type = "BOOLEAN"
            elif "DATETIME" in ctype or "TIMESTAMP" in ctype:
                mysql_type = "DATETIME(6)"
            elif "JSON" in ctype:
                mysql_type = "JSON"
            elif "TEXT" in ctype or "CLOB" in ctype:
                mysql_type = "LONGTEXT"
            else:
                m = re.search(r"\((\d+)\)", ctype)
                length = m.group(1) if m else "500"
                mysql_type = f"VARCHAR({length})"

            col_defs.append(f"`{name}` {mysql_type}")

        cur.execute(f"DROP TABLE IF EXISTS `{table}`")
        cur.execute(f"CREATE TABLE `{table}` ({', '.join(col_defs)}) ENGINE=InnoDB")

        rows = src.execute(f'SELECT * FROM "{table}"').fetchall()
        if rows:
            placeholders = ", ".join(["%s"] * len(columns))
            col_names = ", ".join([f"`{c}`" for c in columns])
            insert_sql = f"INSERT INTO `{table}` ({col_names}) VALUES ({placeholders})"

            batch_size = 5000
            for i in range(0, len(rows), batch_size):
                batch = [tuple(row) for row in rows[i : i + batch_size]]
                cur.executemany(insert_sql, batch)
            conn.commit()

        print(f"  {table}: {len(rows)} rows")

    conn.commit()
    conn.close()
    src.close()
    return len(tables)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    ini_path = os.path.join(script_dir, "wg-dashboard.ini")
    sqlite_main = os.path.join(script_dir, "db", "wgdashboard.db")
    sqlite_job = os.path.join(script_dir, "db", "wgdashboard_job.db")

    if not os.path.isfile(sqlite_main):
        print("No SQLite database found — nothing to migrate.")
        return

    factory = lambda: get_mysql_connection(ini_path)

    print("Migrating main database...")
    n1 = migrate_db(sqlite_main, "wgdashboard", factory)
    print(f"  ✅ {n1} tables migrated")

    print("Migrating job database...")
    n2 = migrate_db(sqlite_job, "wgdashboard_job", factory)
    print(f"  ✅ {n2} tables migrated")

    print("Migration complete!")


if __name__ == "__main__":
    main()
