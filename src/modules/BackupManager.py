"""
BackupManager — creates and manages WGDashboard backups.

Supports:
  - Global snapshots  (all configs + DB + settings)
  - Per-config backups (single .conf + related DB tables)
  - List / delete / download (tar.gz) for both types
  - SHA-256 integrity verification
"""

import hashlib
import json
import os
import re
import shutil
import tarfile
import threading
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import inspect, text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST_VERSION = "1"

# Tables that belong to the "dashboard" bucket in global snapshots
DASHBOARD_TABLES = {
    "DashboardWebHooks",
    "DashboardWebHookSessions",
    "PeerJobs",
    "PeerShareLinks",
    "ConfigurationsInfo",
    "DashboardClients",
    "DashboardOIDCClients",
    "DashboardClientsInfo",
    "DashboardClientsTOTP",
    "DashboardClientConfigAccess",
    "DashboardClientsPeerAssignment",
    "DashboardAPIKeys",
    "DashboardClientsPasswordResetLink",
}

# Per-config table suffixes (the config name is the prefix)
CONFIG_TABLE_SUFFIXES = [
    "",                        # <config_name>
    "_restrict_access",        # <config_name>_restrict_access
    "_transfer",               # <config_name>_transfer
    "_deleted",                # <config_name>_deleted
    "_history_endpoint",       # <config_name>_history_endpoint
]

# Suffixes to EXCLUDE from per-config backups (large, append-only data)
CONFIG_TABLE_SUFFIXES_SKIP_PERCONFIG = {"_transfer", "_history_endpoint"}


class BackupManager:
    """Handles creation, listing, deletion, download and integrity verification
    of WGDashboard backups."""

    def __init__(
        self,
        backup_path: str,
        wg_conf_path: str,
        awg_conf_path: str,
        ini_path: str,
        db_engine,
    ):
        self.backup_path = backup_path
        self.wg_conf_path = wg_conf_path
        self.awg_conf_path = awg_conf_path
        self.ini_path = ini_path
        self.db_engine = db_engine

        # No global lock — sqlite3.backup() is thread-safe and file ops use unique dirs
        self._lock = None  # Kept for reference but not used

        # Ensure directory structure exists
        os.makedirs(os.path.join(self.backup_path, "global"), exist_ok=True)
        os.makedirs(os.path.join(self.backup_path, "per-config"), exist_ok=True)
        os.makedirs(os.path.join(self.backup_path, "downloads"), exist_ok=True)

    # -----------------------------------------------------------------------
    # Public API — Global Snapshots
    # -----------------------------------------------------------------------

    def createGlobalSnapshot(
        self, trigger: str, event_detail: Optional[str] = None
    ) -> dict:
        """Create a full global snapshot.

        Returns a dict with keys: status, name, manifest (on success)
        or status=False, error on failure.
        """
        if True:  # no lock needed — sqlite3.backup() is thread-safe
            ts = self._timestamp()
            name = f"snapshot_{ts}"
            snap_dir = os.path.join(self.backup_path, "global", name)

            try:
                os.makedirs(snap_dir, exist_ok=True)

                # 1. Configs
                configs_dir = os.path.join(snap_dir, "configs")
                os.makedirs(configs_dir, exist_ok=True)
                conf_files = self._collect_conf_files()
                for src in conf_files:
                    shutil.copy2(src, os.path.join(configs_dir, os.path.basename(src)))

                # 2. Settings (ini)
                settings_dir = os.path.join(snap_dir, "settings")
                os.makedirs(settings_dir, exist_ok=True)
                if os.path.isfile(self.ini_path):
                    shutil.copy2(
                        self.ini_path,
                        os.path.join(settings_dir, "wg-dashboard.ini"),
                    )

                # 3. DB export
                db_dir = os.path.join(snap_dir, "db")
                os.makedirs(db_dir, exist_ok=True)

                # 3a. Full DB copy via sqlite3.backup() — non-blocking, includes ALL data
                #     This is used for full database migration/restore
                db_copy_path = os.path.join(db_dir, "wgdashboard.db")
                self._sqlite_backup(db_copy_path)

                # 3b. Lightweight JSON export (without transfer/history) — for granular restore
                all_data = self._export_database(skip_heavy=True)

                peers_data = {
                    k: v for k, v in all_data.items()
                    if k not in DASHBOARD_TABLES
                }
                dashboard_data = {
                    k: v for k, v in all_data.items() if k in DASHBOARD_TABLES
                }

                peers_path = os.path.join(db_dir, "peers.json")
                dashboard_path = os.path.join(db_dir, "dashboard.json")
                with open(peers_path, "w") as f:
                    json.dump(peers_data, f, indent=2, default=str)
                with open(dashboard_path, "w") as f:
                    json.dump(dashboard_data, f, indent=2, default=str)

                # 4. Manifest
                checksums = {}
                components = []

                for root, _dirs, files in os.walk(snap_dir):
                    for fname in sorted(files):
                        if fname == "manifest.json":
                            continue
                        fpath = os.path.join(root, fname)
                        rel = os.path.relpath(fpath, snap_dir)
                        checksums[rel] = self._sha256(fpath)
                        components.append(rel)

                manifest = {
                    "version": MANIFEST_VERSION,
                    "app_version": "v1.3",
                    "type": "global",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "trigger": trigger,
                    "event_detail": event_detail,
                    "components": sorted(components),
                    "checksums": checksums,
                    "size_bytes": self._get_dir_size(snap_dir),
                }

                manifest_path = os.path.join(snap_dir, "manifest.json")
                with open(manifest_path, "w") as f:
                    json.dump(manifest, f, indent=2, default=str)

                return {"status": True, "name": name, "manifest": manifest}

            except Exception as exc:  # noqa: BLE001
                shutil.rmtree(snap_dir, ignore_errors=True)
                return {"status": False, "error": str(exc)}

    def getGlobalSnapshots(self, filter_type: Optional[str] = None) -> list:
        """Return list of global snapshot dicts, newest first.

        Each dict: name, timestamp, trigger, size_bytes, components.
        """
        global_dir = os.path.join(self.backup_path, "global")
        return self._read_snapshot_list(global_dir, filter_type=filter_type)

    def deleteGlobalSnapshot(self, name: str) -> bool:
        """Delete a global snapshot by name. Returns True on success."""
        if True:  # no lock needed — sqlite3.backup() is thread-safe
            snap_dir = os.path.join(self.backup_path, "global", name)
            return self._delete_directory(snap_dir)

    def downloadGlobalSnapshot(self, name: str):
        """Create a .tar.gz of the snapshot in the downloads dir.

        Returns (True, path) on success or (False, None) on failure.
        """
        snap_dir = os.path.join(self.backup_path, "global", name)
        if not os.path.isdir(snap_dir):
            return False, None
        return self._create_tarball(snap_dir, name)

    # -----------------------------------------------------------------------
    # Public API — Per-Config Backups
    # -----------------------------------------------------------------------

    def createConfigBackup(
        self, config_name: str, trigger: str, event_detail: Optional[str] = None
    ) -> dict:
        """Create a per-config backup.

        Returns dict with status=True/False.
        """
        # Find the .conf file
        conf_file = self._find_conf_file(config_name)
        if conf_file is None:
            return {"status": False, "error": f"Config file for '{config_name}' not found"}

        if True:  # no lock needed — sqlite3.backup() is thread-safe
            ts = self._timestamp()
            name = f"{config_name}_{ts}"
            backup_dir = os.path.join(
                self.backup_path, "per-config", config_name, name
            )

            try:
                os.makedirs(backup_dir, exist_ok=True)

                # 1. Copy .conf file
                shutil.copy2(conf_file, os.path.join(backup_dir, f"{config_name}.conf"))

                # 2. DB export — only tables for this config (targeted, not full DB scan)
                target_tables = [config_name]
                for suf in CONFIG_TABLE_SUFFIXES[1:]:
                    if suf not in CONFIG_TABLE_SUFFIXES_SKIP_PERCONFIG:
                        target_tables.append(f"{config_name}{suf}")
                target_tables.append("ConfigurationsInfo")

                config_tables = self._export_tables(target_tables)

                # Filter ConfigurationsInfo to only this config's row
                if "ConfigurationsInfo" in config_tables:
                    config_tables["ConfigurationsInfo"] = [
                        row for row in config_tables["ConfigurationsInfo"]
                        if row.get("Name") == config_name or row.get("ID") == config_name
                    ]

                peers_path = os.path.join(backup_dir, "peers.json")
                with open(peers_path, "w") as f:
                    json.dump(config_tables, f, indent=2, default=str)

                # 3. Manifest
                checksums = {}
                components = []
                for root, _dirs, files in os.walk(backup_dir):
                    for fname in sorted(files):
                        if fname == "manifest.json":
                            continue
                        fpath = os.path.join(root, fname)
                        rel = os.path.relpath(fpath, backup_dir)
                        checksums[rel] = self._sha256(fpath)
                        components.append(rel)

                manifest = {
                    "version": MANIFEST_VERSION,
                    "app_version": "v1.3",
                    "type": "per-config",
                    "config_name": config_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "trigger": trigger,
                    "event_detail": event_detail,
                    "components": sorted(components),
                    "checksums": checksums,
                    "size_bytes": self._get_dir_size(backup_dir),
                }

                manifest_path = os.path.join(backup_dir, "manifest.json")
                with open(manifest_path, "w") as f:
                    json.dump(manifest, f, indent=2, default=str)

                return {"status": True, "name": name, "manifest": manifest}

            except Exception as exc:  # noqa: BLE001
                shutil.rmtree(backup_dir, ignore_errors=True)
                return {"status": False, "error": str(exc)}

    def getConfigBackups(self, config_name: str) -> list:
        """Return list of per-config backup dicts for config_name, newest first."""
        config_dir = os.path.join(self.backup_path, "per-config", config_name)
        if not os.path.isdir(config_dir):
            return []
        return self._read_snapshot_list(config_dir)

    def deleteConfigBackup(self, config_name: str, name: str) -> bool:
        """Delete a per-config backup. Returns True on success."""
        if True:  # no lock needed — sqlite3.backup() is thread-safe
            backup_dir = os.path.join(
                self.backup_path, "per-config", config_name, name
            )
            return self._delete_directory(backup_dir)

    def downloadConfigBackup(self, config_name: str, name: str):
        """Create a .tar.gz of the per-config backup.

        Returns (True, path) or (False, None).
        """
        backup_dir = os.path.join(
            self.backup_path, "per-config", config_name, name
        )
        if not os.path.isdir(backup_dir):
            return False, None
        return self._create_tarball(backup_dir, name)

    # -----------------------------------------------------------------------
    # Restore
    # -----------------------------------------------------------------------

    def restoreFromSnapshot(self, name: str, components: list) -> dict:
        """Restore selected components from a global snapshot.

        Parameters
        ----------
        name:       snapshot directory name (e.g. "snapshot_20240101_120000_000000")
        components: list of component names to restore, any of:
                    "configurations", "dashboard_settings", "webhooks",
                    "peer_jobs", "share_links", "client_portal", "api_keys"

        Returns
        -------
        {"status": True,  "restored": [<component names>]}  on success
        {"status": False, "message": "..."}                 on failure
        """
        snap_dir = os.path.join(self.backup_path, "global", name)

        if not os.path.isdir(snap_dir):
            return {"status": False, "message": f"Snapshot '{name}' not found"}

        if not self.verifyIntegrity(snap_dir):
            return {"status": False, "message": "Integrity check failed — checksums don't match"}

        # Create restore point — backup current state before overwriting
        try:
            self.createGlobalSnapshot(
                trigger="restore_point",
                event_detail=f"pre-restore from {name}",
            )
        except Exception:
            pass

        # Map component names to dashboard DB tables
        _COMPONENT_TABLE_MAP = {
            "webhooks": ["DashboardWebHooks", "DashboardWebHookSessions"],
            "peer_jobs": ["PeerJobs"],
            "share_links": ["PeerShareLinks"],
            "client_portal": [
                "DashboardClients",
                "DashboardOIDCClients",
                "DashboardClientsInfo",
                "DashboardClientsTOTP",
                "DashboardClientConfigAccess",
                "DashboardClientsPeerAssignment",
            ],
            "api_keys": ["DashboardAPIKeys"],
        }

        restored = []

        if True:  # no lock needed — sqlite3.backup() is thread-safe
            # 1. Dashboard settings (ini file)
            if "dashboard_settings" in components:
                ini_backup = os.path.join(snap_dir, "settings", "wg-dashboard.ini")
                if os.path.isfile(ini_backup):
                    shutil.copy2(ini_backup, self.ini_path)
                restored.append("dashboard_settings")

            # 2. Configuration files — replace ALL configs (remove those not in backup)
            if "configurations" in components:
                configs_dir = os.path.join(snap_dir, "configs")
                if os.path.isdir(configs_dir):
                    backup_confs = set(os.listdir(configs_dir))
                    # Remove current .conf files not present in backup
                    for conf_dir in [self.wg_conf_path, self.awg_conf_path]:
                        if not conf_dir or not os.path.isdir(conf_dir):
                            continue
                        for fname in os.listdir(conf_dir):
                            if fname.endswith(".conf") and fname not in backup_confs:
                                os.remove(os.path.join(conf_dir, fname))
                    # Copy backup configs
                    for fname in backup_confs:
                        if not fname.endswith(".conf"):
                            continue
                        src = os.path.join(configs_dir, fname)
                        dest = os.path.join(self.wg_conf_path, fname)
                        shutil.copy2(src, dest)
                restored.append("configurations")

            # 3. Dashboard DB components
            dashboard_json = os.path.join(snap_dir, "db", "dashboard.json")
            if os.path.isfile(dashboard_json):
                with open(dashboard_json) as f:
                    dashboard_data = json.load(f)

                warnings = []
                db_components = [c for c in components if c in _COMPONENT_TABLE_MAP]
                if db_components:
                    with self.db_engine.begin() as conn:
                        for comp in db_components:
                            for table in _COMPONENT_TABLE_MAP[comp]:
                                if table not in dashboard_data:
                                    continue
                                if not self._is_valid_table_name(table):
                                    continue
                                try:
                                    rows = dashboard_data[table]
                                    conn.execute(text(f'DELETE FROM "{table}"'))
                                    if rows:
                                        cols = list(rows[0].keys())
                                        col_names = ", ".join(f'"{c}"' for c in cols)
                                        col_params = ", ".join(f":col_{c}" for c in cols)
                                        conn.execute(
                                            text(f'INSERT INTO "{table}" ({col_names}) VALUES ({col_params})'),
                                            [{f"col_{k}": v for k, v in row.items()} for row in rows],
                                        )
                                except Exception as e:  # noqa: BLE001
                                    warnings.append(f"Failed to restore table {table}: {str(e)}")
                            restored.append(comp)

            # 4. Database restore (alongside configurations)
            if "configurations" in components:
                # Prefer full .db file restore (exact copy, includes transfer/history)
                db_backup = os.path.join(snap_dir, "db", "wgdashboard.db")
                if os.path.isfile(db_backup):
                    self._sqlite_restore(db_backup)
                    restored.append("full_database")
                else:
                    # Fallback: JSON-based restore (older snapshots without .db file)
                    # Must drop ALL peer tables first, then insert only what's in backup
                    peers_json = os.path.join(snap_dir, "db", "peers.json")
                    if os.path.isfile(peers_json):
                        with open(peers_json) as f:
                            peers_data = json.load(f)
                        with self.db_engine.begin() as conn:
                            # Drop all existing per-config tables
                            try:
                                inspector = inspect(self.db_engine)
                                for tbl in inspector.get_table_names():
                                    if tbl not in DASHBOARD_TABLES and self._is_valid_table_name(tbl):
                                        conn.execute(text(f'DELETE FROM "{tbl}"'))
                            except Exception:
                                pass
                            # Insert backup data
                            for table, rows in peers_data.items():
                                if not self._is_valid_table_name(table):
                                    continue
                                try:
                                    if rows:
                                        cols = list(rows[0].keys())
                                        col_names = ", ".join(f'"{c}"' for c in cols)
                                        col_params = ", ".join(f":col_{c}" for c in cols)
                                        conn.execute(
                                            text(f'INSERT INTO "{table}" ({col_names}) VALUES ({col_params})'),
                                            [{f"col_{k}": v for k, v in row.items()} for row in rows],
                                        )
                                except Exception as e:  # noqa: BLE001
                                    warnings.append(f"Failed to restore table {table}: {str(e)}")

        return {"status": True, "restored": restored, "warnings": warnings}

    def restoreConfigBackup(self, config_name: str, name: str) -> dict:
        """Restore a single per-config backup (.conf file + peers DB tables).

        Returns
        -------
        {"status": True,  "restored": config_name}  on success
        {"status": False, "message": "..."}          on failure
        """
        backup_dir = os.path.join(self.backup_path, "per-config", config_name, name)

        if not os.path.isdir(backup_dir):
            return {"status": False, "message": f"Backup '{name}' not found for config '{config_name}'"}

        if not self.verifyIntegrity(backup_dir):
            return {"status": False, "message": "Integrity check failed — checksums don't match"}

        # Create restore point — backup current state before overwriting
        try:
            self.createConfigBackup(
                config_name=config_name,
                trigger="restore_point",
                event_detail=f"pre-restore from {name}",
            )
        except Exception:
            pass

        if True:  # no lock needed — sqlite3.backup() is thread-safe
            # 1. Restore .conf file
            conf_backup = os.path.join(backup_dir, f"{config_name}.conf")
            if os.path.isfile(conf_backup):
                # Determine destination directory
                awg_candidate = os.path.join(self.awg_conf_path, f"{config_name}.conf")
                wg_candidate = os.path.join(self.wg_conf_path, f"{config_name}.conf")
                if os.path.isfile(awg_candidate):
                    dest = awg_candidate
                else:
                    dest = wg_candidate
                shutil.copy2(conf_backup, dest)

            # 2. Restore peers DB tables
            warnings = []
            peers_json = os.path.join(backup_dir, "peers.json")
            if os.path.isfile(peers_json):
                with open(peers_json) as f:
                    peers_data = json.load(f)
                with self.db_engine.begin() as conn:
                    for table, rows in peers_data.items():
                        # Skip legacy SQL migration entries
                        if table == "_legacy_sql":
                            continue
                        if not self._is_valid_table_name(table):
                            continue
                        try:
                            conn.execute(text(f'DELETE FROM "{table}"'))
                            if rows:
                                cols = list(rows[0].keys())
                                col_names = ", ".join(f'"{c}"' for c in cols)
                                col_params = ", ".join(f":col_{c}" for c in cols)
                                conn.execute(
                                    text(f'INSERT INTO "{table}" ({col_names}) VALUES ({col_params})'),
                                    [{f"col_{k}": v for k, v in row.items()} for row in rows],
                                )
                        except Exception as e:  # noqa: BLE001
                            warnings.append(f"Failed to restore table {table}: {str(e)}")

        return {"status": True, "restored": config_name, "warnings": warnings}

    # -----------------------------------------------------------------------
    # Rotation and Storage Limits
    # -----------------------------------------------------------------------

    def enforceRotation(
        self,
        daily_keep: int,
        weekly_keep: int,
        monthly_keep: int,
        max_storage_mb: float,
    ) -> None:
        """Delete old snapshots according to keep limits and storage cap.

        Keep limits apply per trigger type:
          - "scheduled_daily"   → daily_keep
          - "scheduled_weekly"  → weekly_keep
          - "scheduled_monthly" → monthly_keep

        After applying keep limits, if total size of global/ exceeds
        max_storage_mb, the oldest non-manual snapshots are deleted until
        the size fits.

        Manual snapshots are NEVER auto-deleted.
        """
        # filter_type uses raw manifest trigger values; type map for keep limits
        keep_map = {
            "scheduled_daily": daily_keep,
            "scheduled_weekly": weekly_keep,
            "scheduled_monthly": monthly_keep,
        }

        # Apply per-trigger keep limits (newest first, delete oldest)
        for trigger, keep in keep_map.items():
            snapshots = self.getGlobalSnapshots(filter_type=trigger)
            # snapshots already sorted newest-first
            to_delete = snapshots[keep:]
            for snap in to_delete:
                self.deleteGlobalSnapshot(snap["name"])

        # Enforce total storage cap
        max_bytes = max_storage_mb * 1024 * 1024
        global_dir = os.path.join(self.backup_path, "global")

        while True:
            current_size = self._get_dir_size(global_dir)
            if current_size <= max_bytes:
                break

            # Get all non-manual snapshots, oldest first
            all_snapshots = self.getGlobalSnapshots()
            non_manual = [s for s in all_snapshots if s["type"] != "manual"]
            if not non_manual:
                break  # Nothing left to delete (only manual snapshots remain)

            # Delete oldest non-manual snapshot
            oldest = non_manual[-1]
            deleted = self.deleteGlobalSnapshot(oldest["name"])
            if not deleted:
                break  # Safety: avoid infinite loop if deletion fails

    def enforcePerConfigRotation(self, config_name: str, keep: int) -> None:
        """Delete oldest per-config backups when count exceeds keep limit.

        Parameters
        ----------
        config_name: configuration name
        keep:        maximum number of backups to retain
        """
        backups = self.getConfigBackups(config_name)
        # backups already sorted newest-first
        to_delete = backups[keep:]
        for backup in to_delete:
            self.deleteConfigBackup(config_name, backup["name"])

    # -----------------------------------------------------------------------
    # Integrity
    # -----------------------------------------------------------------------

    def verifyIntegrity(self, snapshot_dir: str) -> bool:
        """Verify SHA-256 checksums of all files listed in manifest.json.

        Returns True if all checksums match, False otherwise.
        """
        manifest_path = os.path.join(snapshot_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            return False

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except Exception:  # noqa: BLE001
            return False

        checksums = manifest.get("checksums", {})
        for rel_path, expected in checksums.items():
            fpath = os.path.join(snapshot_dir, rel_path)
            if not os.path.isfile(fpath):
                return False
            if self._sha256(fpath) != expected:
                return False

        return True

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _is_valid_table_name(self, name: str) -> bool:
        """Validate a table name from a backup file before using it in SQL."""
        valid_globals = {
            "DashboardWebHooks", "DashboardWebHookSessions", "PeerJobs",
            "PeerShareLinks", "ConfigurationsInfo", "DashboardClients",
            "DashboardOIDCClients", "DashboardClientsInfo", "DashboardClientsTOTP",
            "DashboardClientConfigAccess", "DashboardClientsPeerAssignment",
            "DashboardAPIKeys", "DashboardClientsPasswordResetLink",
        }
        if name in valid_globals:
            return True
        # Per-config tables: alphanumeric + hyphens/underscores, optionally with suffix
        return bool(re.match(
            r'^[a-zA-Z0-9_-]+(_restrict_access|_transfer|_deleted|_history_endpoint)?$',
            name,
        ))

    def _timestamp(self) -> str:
        """Return current UTC time as YYYYMMDD_HHMMSS_ffffff (microseconds)."""
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

    def _sha256(self, filepath: str) -> str:
        """Return 'sha256:<hexdigest>' for a file."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"

    def _collect_conf_files(self) -> list:
        """Return list of absolute paths to all .conf files in wg/awg dirs."""
        results = []
        for conf_dir in (self.wg_conf_path, self.awg_conf_path):
            if not os.path.isdir(conf_dir):
                continue
            for fname in os.listdir(conf_dir):
                if fname.endswith(".conf"):
                    results.append(os.path.join(conf_dir, fname))
        return results

    def _find_conf_file(self, config_name: str) -> Optional[str]:
        """Find <config_name>.conf in wg or awg directories."""
        fname = f"{config_name}.conf"
        for conf_dir in (self.wg_conf_path, self.awg_conf_path):
            candidate = os.path.join(conf_dir, fname)
            if os.path.isfile(candidate):
                return candidate
        return None

    def _sqlite_backup(self, dest_path: str) -> bool:
        """Create a non-blocking copy of the SQLite database using sqlite3.backup().

        This is atomic and does NOT block concurrent writers (background threads
        can continue writing transfer data while the backup runs).
        Typically completes in <100ms even for large databases.
        """
        import sqlite3
        try:
            db_url = str(self.db_engine.url)
            # Extract file path from SQLAlchemy URL (sqlite:///path/to/db)
            if "sqlite" not in db_url:
                return False  # Not SQLite, skip
            db_path = db_url.split("///")[-1] if "///" in db_url else db_url.split("//")[-1]
            if not os.path.isfile(db_path):
                return False

            src_conn = sqlite3.connect(db_path)
            dst_conn = sqlite3.connect(dest_path)
            src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()
            return True
        except Exception:
            return False

    def _sqlite_restore(self, src_path: str) -> bool:
        """Restore the SQLite database from a backup .db file.

        Replaces the live database file with the backup copy.
        The SQLAlchemy engine will pick up the new data on next connection.
        """
        import sqlite3
        try:
            db_url = str(self.db_engine.url)
            if "sqlite" not in db_url:
                return False
            db_path = db_url.split("///")[-1] if "///" in db_url else db_url.split("//")[-1]

            # Dispose all connections so the file is not locked
            self.db_engine.dispose()

            # Use sqlite3.backup() in reverse — from backup file to live DB
            src_conn = sqlite3.connect(src_path)
            dst_conn = sqlite3.connect(db_path)
            src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()
            return True
        except Exception:
            return False

    def _export_database(self, skip_heavy: bool = True) -> dict:
        """Export all tables from the database as {table_name: [row_dict, ...]}.

        If skip_heavy=True (default), skips _transfer and _history_endpoint tables
        which can contain hundreds of thousands of rows and are not needed for restore.
        """
        try:
            inspector = inspect(self.db_engine)
            table_names = inspector.get_table_names()
            if skip_heavy:
                table_names = [
                    t for t in table_names
                    if not any(t.endswith(s) for s in CONFIG_TABLE_SUFFIXES_SKIP_PERCONFIG)
                ]
        except Exception:  # noqa: BLE001
            return {}
        return self._export_tables(table_names)

    def _export_tables(self, table_names: list) -> dict:
        """Export specific tables from the database as {table_name: [row_dict, ...]}."""
        result = {}
        try:
            with self.db_engine.connect() as conn:
                for table_name in table_names:
                    try:
                        rows = conn.execute(text(f'SELECT * FROM "{table_name}"'))
                        keys = list(rows.keys())
                        result[table_name] = [dict(zip(keys, row)) for row in rows]
                    except Exception:  # noqa: BLE001
                        result[table_name] = []
        except Exception:  # noqa: BLE001
            pass
        return result

    def _get_dir_size(self, path: str) -> int:
        """Return total size in bytes of all files under path."""
        total = 0
        for dirpath, _dirs, files in os.walk(path):
            for fname in files:
                fpath = os.path.join(dirpath, fname)
                try:
                    total += os.path.getsize(fpath)
                except OSError:
                    pass
        return total

    # Map raw trigger values stored in manifest to simplified frontend type names
    _TRIGGER_TYPE_MAP = {
        "scheduled_daily": "daily",
        "scheduled_weekly": "weekly",
        "scheduled_monthly": "monthly",
        "event": "auto",
        "manual": "manual",
        "restore_point": "restore_point",
        "legacy_migration": "legacy",
    }

    def _read_snapshot_list(
        self, directory: str, filter_type: Optional[str] = None
    ) -> list:
        """Read manifest files from immediate subdirs and return summary list."""
        if not os.path.isdir(directory):
            return []

        snapshots = []
        for entry in os.scandir(directory):
            if not entry.is_dir():
                continue
            manifest_path = os.path.join(entry.path, "manifest.json")
            if not os.path.isfile(manifest_path):
                continue
            try:
                with open(manifest_path) as f:
                    m = json.load(f)
                raw_trigger = m.get("trigger", "")
                if filter_type is not None and raw_trigger != filter_type:
                    continue
                simplified_type = self._TRIGGER_TYPE_MAP.get(raw_trigger, raw_trigger)
                snapshots.append(
                    {
                        "name": entry.name,
                        "date": m.get("timestamp", ""),
                        "type": simplified_type,
                        "size": m.get("size_bytes", 0),
                        "event": m.get("event_detail", ""),
                        "components": m.get("components", []),
                    }
                )
            except Exception:  # noqa: BLE001
                continue

        # Newest first — sort by date string (ISO-8601 sorts lexicographically)
        snapshots.sort(key=lambda s: s["date"], reverse=True)
        return snapshots

    def _delete_directory(self, path: str) -> bool:
        """Remove directory if it exists. Returns True on success."""
        if not os.path.isdir(path):
            return False
        try:
            shutil.rmtree(path)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _create_tarball(self, source_dir: str, name: str):
        """Create a .tar.gz of source_dir in the downloads subdir.

        Returns (True, tar_path) or (False, None).
        """
        downloads_dir = os.path.join(self.backup_path, "downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        tar_path = os.path.join(downloads_dir, f"{name}.tar.gz")
        try:
            with tarfile.open(tar_path, "w:gz") as tar:
                tar.add(source_dir, arcname=name)
            return True, tar_path
        except Exception:  # noqa: BLE001
            return False, None
