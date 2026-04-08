#!/usr/bin/env python3
"""Convert old SQLite .db backup files to MySQL .sql dump format.

Scans all global snapshots and per-config backups for wgdashboard.db files.
For each one, reads all tables from SQLite and generates a MySQL-compatible
SQL dump file (wgdashboard.sql). The original .db file is kept as-is.

Usage: cd /opt/WGDashboard/src && ./venv/bin/python3 convert_old_backups.py
"""

import os
import re
import sqlite3
import sys


def sqlite_to_sql_dump(sqlite_path: str, sql_path: str, db_name: str = "wgdashboard") -> bool:
    """Convert a SQLite .db file to a MySQL-compatible .sql dump."""
    try:
        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row

        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()]

        if not tables:
            conn.close()
            return False

        with open(sql_path, "w") as f:
            f.write(f"-- Converted from SQLite: {os.path.basename(sqlite_path)}\n")
            f.write(f"-- Tables: {len(tables)}\n\n")
            f.write(f"USE `{db_name}`;\n\n")
            f.write("SET FOREIGN_KEY_CHECKS=0;\n\n")

            for table in sorted(tables):
                cols_info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()

                # Build CREATE TABLE
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

                    col_defs.append(f"  `{name}` {mysql_type}")

                f.write(f"DROP TABLE IF EXISTS `{table}`;\n")
                f.write(f"CREATE TABLE `{table}` (\n")
                f.write(",\n".join(col_defs))
                f.write("\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n")

                # Export data
                rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
                if rows:
                    # Batch inserts
                    col_names = ", ".join(f"`{c}`" for c in columns)
                    batch_size = 500
                    for i in range(0, len(rows), batch_size):
                        batch = rows[i:i + batch_size]
                        values_list = []
                        for row in batch:
                            vals = []
                            for v in tuple(row):
                                if v is None:
                                    vals.append("NULL")
                                elif isinstance(v, (int, float)):
                                    vals.append(str(v))
                                else:
                                    escaped = str(v).replace("\\", "\\\\").replace("'", "\\'")
                                    vals.append(f"'{escaped}'")
                            values_list.append(f"({', '.join(vals)})")

                        f.write(f"INSERT INTO `{table}` ({col_names}) VALUES\n")
                        f.write(",\n".join(values_list))
                        f.write(";\n")
                    f.write("\n")

            f.write("SET FOREIGN_KEY_CHECKS=1;\n")

        conn.close()
        return True

    except Exception as e:
        print(f"  ERROR converting {sqlite_path}: {e}")
        return False


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backup_path = os.path.join(script_dir, "backups")

    if not os.path.isdir(backup_path):
        print("No backups directory found.")
        return

    converted = 0
    skipped = 0

    # Scan global snapshots
    global_dir = os.path.join(backup_path, "global")
    if os.path.isdir(global_dir):
        for snap in sorted(os.listdir(global_dir)):
            db_path = os.path.join(global_dir, snap, "db", "wgdashboard.db")
            sql_path = os.path.join(global_dir, snap, "db", "wgdashboard.sql")

            if not os.path.isfile(db_path):
                continue
            if os.path.isfile(sql_path):
                skipped += 1
                continue
            if os.path.getsize(db_path) == 0:
                skipped += 1
                continue

            print(f"  Converting {snap}...")
            if sqlite_to_sql_dump(db_path, sql_path):
                size_kb = os.path.getsize(sql_path) // 1024
                print(f"    -> wgdashboard.sql ({size_kb} KB)")
                converted += 1
            else:
                print(f"    -> FAILED")

    # Scan per-config backups
    perconfig_dir = os.path.join(backup_path, "per-config")
    if os.path.isdir(perconfig_dir):
        for config_name in os.listdir(perconfig_dir):
            config_dir = os.path.join(perconfig_dir, config_name)
            if not os.path.isdir(config_dir):
                continue
            for backup_name in os.listdir(config_dir):
                # Per-config backups don't have .db files typically, but check anyway
                db_path = os.path.join(config_dir, backup_name, "wgdashboard.db")
                if os.path.isfile(db_path) and os.path.getsize(db_path) > 0:
                    sql_path = os.path.join(config_dir, backup_name, "wgdashboard.sql")
                    if not os.path.isfile(sql_path):
                        print(f"  Converting per-config {config_name}/{backup_name}...")
                        if sqlite_to_sql_dump(db_path, sql_path):
                            converted += 1

    print(f"\nDone: {converted} converted, {skipped} skipped (already have .sql or empty)")


if __name__ == "__main__":
    main()
