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
import time
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

        # No global lock — backup operations use unique directories
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
        if True:  # no lock needed
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
                #    - JSON dumps (peers.json + dashboard.json) for inspection/preview
                #      and as a portable fallback when full SQL dump is unavailable.
                #    - Full SQL dump (wgdashboard.sql / wgdashboard.db) for authoritative
                #      restore — guarantees the snapshot contains the *entire* database
                #      regardless of what the JSON exporter knows about.
                db_dir = os.path.join(snap_dir, "db")
                os.makedirs(db_dir, exist_ok=True)

                all_data = self._export_database(skip_heavy=True)

                # Update shared transfer dump (one copy for all snapshots)
                try:
                    transfer_dump_path = os.path.join(self.backup_path, "transfer_dump.sql")
                    self._dump_transfer_tables(transfer_dump_path)
                except Exception:
                    pass

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

                # Full DB dump alongside JSON (mysqldump for MySQL, sqlite3.backup for SQLite).
                # Best-effort: if the dump cannot be created (missing mysqldump binary,
                # in-memory sqlite, mocked engine in tests, …) we keep the JSON exports
                # as fallback rather than failing the whole snapshot. The manifest
                # records whether the full SQL/sqlite dump landed; UI shows the badge.
                db_type = self._get_db_type()
                full_db_path = None
                if db_type == "mysql":
                    full_db_path = os.path.join(db_dir, "wgdashboard.sql")
                elif db_type == "sqlite":
                    full_db_path = os.path.join(db_dir, "wgdashboard.db")
                full_db_ok = False
                if full_db_path is not None:
                    full_db_ok = self._full_db_backup(full_db_path)
                    if not full_db_ok:
                        # Remove any partial file so manifest doesn't checksum a bad dump.
                        try:
                            if os.path.isfile(full_db_path):
                                os.remove(full_db_path)
                        except OSError:
                            pass

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

                self._record_event("global", trigger, "success", name=name,
                                   size=manifest.get("size_bytes"))
                return {"status": True, "name": name, "manifest": manifest}

            except Exception as exc:  # noqa: BLE001
                shutil.rmtree(snap_dir, ignore_errors=True)
                self._record_event("global", trigger, "failure", error=exc)
                return {"status": False, "error": str(exc)}

    def getSnapshotDetails(self, name: str) -> dict:
        """Return detailed contents of a global snapshot for preview."""
        snap_dir = os.path.join(self.backup_path, "global", name)
        if not os.path.isdir(snap_dir):
            return None

        details = {"configs": [], "dashboard": {}, "has_full_db": False}

        # 1. List config files with basic info
        configs_dir = os.path.join(snap_dir, "configs")
        if os.path.isdir(configs_dir):
            for f in sorted(os.listdir(configs_dir)):
                if f.endswith(".conf"):
                    details["configs"].append({"name": f.replace(".conf", "")})

        # 2. Read peers.json to get peer counts per config
        peers_path = os.path.join(snap_dir, "db", "peers.json")
        if os.path.isfile(peers_path):
            try:
                with open(peers_path) as f:
                    peers_data = json.load(f)
                # Count peers per config (tables without suffixes = main peer tables)
                for conf in details["configs"]:
                    name_key = conf["name"]
                    if name_key in peers_data:
                        conf["peers"] = len(peers_data[name_key])
                    else:
                        conf["peers"] = 0
                    # Check restricted
                    restricted_key = f"{name_key}_restrict_access"
                    if restricted_key in peers_data:
                        conf["restricted"] = len(peers_data[restricted_key])
            except Exception:
                pass

        # 3. Read dashboard.json to get component counts
        dashboard_path = os.path.join(snap_dir, "db", "dashboard.json")
        if os.path.isfile(dashboard_path):
            try:
                with open(dashboard_path) as f:
                    dashboard_data = json.load(f)
                details["dashboard"] = {
                    "webhooks": len(dashboard_data.get("DashboardWebHooks", [])),
                    "clients": len(dashboard_data.get("DashboardClients", [])),
                    "peer_jobs": len(dashboard_data.get("PeerJobs", [])),
                    "share_links": len(dashboard_data.get("PeerShareLinks", [])),
                    "api_keys": len(dashboard_data.get("DashboardAPIKeys", [])),
                }
            except Exception:
                pass

        # 4. Check for full DB file
        details["has_full_db"] = (
            os.path.isfile(os.path.join(snap_dir, "db", "wgdashboard.sql"))
            or os.path.isfile(os.path.join(snap_dir, "db", "wgdashboard.db"))
        )
        details["has_shared_transfer"] = os.path.isfile(
            os.path.join(self.backup_path, "transfer_dump.sql")
        )

        # 5. Settings
        details["has_settings"] = os.path.isfile(os.path.join(snap_dir, "settings", "wg-dashboard.ini"))

        return details

    def getGlobalSnapshots(self, filter_type: Optional[str] = None) -> list:
        """Return list of global snapshot dicts, newest first.

        Each dict: name, timestamp, trigger, size_bytes, components.
        """
        global_dir = os.path.join(self.backup_path, "global")
        return self._read_snapshot_list(global_dir, filter_type=filter_type)

    def deleteGlobalSnapshot(self, name: str) -> bool:
        """Delete a global snapshot by name. Returns True on success."""
        if True:  # no lock needed
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

        if True:  # no lock needed
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

                # Per-config SQL dump (only this config's tables) — gives an
                # authoritative DB-level fallback alongside the JSON export.
                # Best-effort: skipped silently for non-MySQL backends or when
                # mysqldump is unavailable; JSON remains authoritative.
                if self._get_db_type() == "mysql":
                    sql_path = os.path.join(backup_dir, f"{config_name}.sql")
                    if not self._dump_specific_tables(sql_path, target_tables):
                        try:
                            if os.path.isfile(sql_path):
                                os.remove(sql_path)
                        except OSError:
                            pass

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

                self._record_event("per-config", trigger, "success", name=name,
                                   size=manifest.get("size_bytes"))
                return {"status": True, "name": name, "manifest": manifest}

            except Exception as exc:  # noqa: BLE001
                shutil.rmtree(backup_dir, ignore_errors=True)
                self._record_event("per-config", trigger, "failure",
                                   name=config_name, error=exc)
                return {"status": False, "error": str(exc)}

    def getConfigBackups(self, config_name: str) -> list:
        """Return list of per-config backup dicts for config_name, newest first."""
        config_dir = os.path.join(self.backup_path, "per-config", config_name)
        if not os.path.isdir(config_dir):
            return []
        return self._read_snapshot_list(config_dir)

    def deleteConfigBackup(self, config_name: str, name: str) -> bool:
        """Delete a per-config backup. Returns True on success."""
        if True:  # no lock needed
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
                    "configurations"      — wg/awg .conf files only
                    "full_database"       — replace entire DB from SQL/sqlite dump
                    "dashboard_settings"  — wg-dashboard.ini
                    "webhooks", "peer_jobs", "share_links",
                    "client_portal", "api_keys"  — JSON-based partial restores
                                                   (ignored when full_database is selected)

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

        if True:  # no lock needed
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

            warnings = []

            # 3. Full database restore — independent component.
            #    When selected, this REPLACES the entire DB from the SQL/sqlite
            #    dump in the snapshot. JSON-based partial component restores
            #    below are skipped (full DB already covers them).
            full_db_done = False
            if "full_database" in components:
                db_sql = os.path.join(snap_dir, "db", "wgdashboard.sql")
                db_sqlite = os.path.join(snap_dir, "db", "wgdashboard.db")
                src = db_sql if os.path.isfile(db_sql) else (
                    db_sqlite if os.path.isfile(db_sqlite) else None
                )
                if src is None:
                    warnings.append(
                        "full_database requested but no SQL/sqlite dump found in snapshot — "
                        "this snapshot was created before DB-in-backup support"
                    )
                else:
                    if self._full_db_restore(src):
                        restored.append("full_database")
                        full_db_done = True
                    else:
                        warnings.append("full_database restore failed (see logs)")

            # 4. JSON-based partial DB component restores.
            #    Skipped if full_database already replaced the entire DB.
            if not full_db_done:
                dashboard_json = os.path.join(snap_dir, "db", "dashboard.json")
                if os.path.isfile(dashboard_json):
                    with open(dashboard_json) as f:
                        dashboard_data = json.load(f)

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
                                        qt = self._quote_id(table)
                                        conn.execute(text(f'DELETE FROM {qt}'))
                                        if rows:
                                            cols = list(rows[0].keys())
                                            col_names = self._quote_cols(cols)
                                            col_params = ", ".join(f":col_{c}" for c in cols)
                                            conn.execute(
                                                text(f'INSERT INTO {qt} ({col_names}) VALUES ({col_params})'),
                                                [{f"col_{k}": v for k, v in row.items()} for row in rows],
                                            )
                                    except Exception as e:  # noqa: BLE001
                                        warnings.append(f"Failed to restore table {table}: {str(e)}")
                                restored.append(comp)

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

        if True:  # no lock needed
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
                            qt = self._quote_id(table)
                            conn.execute(text(f'DELETE FROM {qt}'))
                            if rows:
                                cols = list(rows[0].keys())
                                col_names = self._quote_cols(cols)
                                col_params = ", ".join(f":col_{c}" for c in cols)
                                conn.execute(
                                    text(f'INSERT INTO {qt} ({col_names}) VALUES ({col_params})'),
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
        # Clear leftovers from any failed/half-deleted snapshots first.
        self.cleanupOrphans()

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

        # Enforce total storage cap (disk-aware, not a bare configured MB)
        max_bytes = self.effectiveStorageCapBytes(max_storage_mb)
        global_dir = os.path.join(self.backup_path, "global")

        while True:
            current_size = self._get_dir_size(global_dir)
            if current_size <= max_bytes:
                break

            # All snapshots, newest first.
            all_snapshots = self.getGlobalSnapshots()
            # NEVER delete the most-recent snapshot for the storage cap — we
            # always want to keep the latest backup, even if it alone exceeds
            # the cap. Otherwise a freshly-created scheduled snapshot (the only
            # non-manual candidate) would be deleted right after creation and
            # scheduled backups would never persist.
            newest_name = all_snapshots[0]["name"] if all_snapshots else None
            non_manual = [
                s for s in all_snapshots
                if s["type"] != "manual" and s["name"] != newest_name
            ]
            if not non_manual:
                break  # Nothing left to delete (newest + manual are protected)

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

    def _quote_id(self, name: str) -> str:
        """Dialect-aware identifier quoting (backticks for MySQL/MariaDB,
        double-quotes for SQLite/Postgres). Hard-coded double-quotes errored
        on MariaDB with `1064: SQL syntax ... near '"X"'`."""
        return self.db_engine.dialect.identifier_preparer.quote(name)

    def _quote_cols(self, cols: list[str]) -> str:
        """Comma-separated quoted column list, dialect-aware."""
        return ", ".join(self._quote_id(c) for c in cols)

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

    def _dump_transfer_tables(self, dest_path: str) -> bool:
        """Dump only transfer and history_endpoint tables to a shared SQL file.

        This is kept as one copy for all snapshots since transfer data is
        append-only — each new dump contains all previous data.
        """
        import subprocess
        db_type = self._get_db_type()

        if db_type == "mysql":
            creds = self._get_mysql_credentials()
            # Get transfer/history table names
            try:
                with self.db_engine.connect() as conn:
                    result = conn.execute(text(
                        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                        f"WHERE TABLE_SCHEMA = '{creds['database']}' "
                        "AND (TABLE_NAME LIKE '%_transfer' OR TABLE_NAME LIKE '%_history_endpoint')"
                    ))
                    tables = [row[0] for row in result]
            except Exception:
                return False

            if not tables:
                return False

            cmd = [
                "mysqldump",
                f"--host={creds['host']}",
                f"--port={creds['port']}",
                f"--user={creds['user']}",
                f"--password={creds['password']}",
                "--single-transaction",
                creds["database"],
            ] + tables

            with open(dest_path, "w") as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=120)
            return result.returncode == 0

        return False

    def _dump_specific_tables(self, dest_path: str, tables: list) -> bool:
        """Dump a specific set of MySQL tables to a SQL file.

        Skips silently if not MySQL or if no tables exist. Used by per-config
        backups to capture only the tables that belong to one configuration.
        """
        import subprocess
        if self._get_db_type() != "mysql":
            return False

        creds = self._get_mysql_credentials()
        try:
            with self.db_engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                    f"WHERE TABLE_SCHEMA = '{creds['database']}'"
                ))
                existing = {row[0] for row in result}
        except Exception:
            return False

        tables_to_dump = [t for t in tables if t in existing]
        if not tables_to_dump:
            return False

        cmd = [
            "mysqldump",
            f"--host={creds['host']}",
            f"--port={creds['port']}",
            f"--user={creds['user']}",
            f"--password={creds['password']}",
            "--single-transaction",
            "--no-tablespaces",
            creds["database"],
        ] + tables_to_dump

        try:
            with open(dest_path, "w") as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=120)
            return result.returncode == 0
        except Exception:
            return False

    def _get_db_type(self) -> str:
        """Return 'mysql', 'postgresql', or 'sqlite' based on engine URL."""
        url = str(self.db_engine.url)
        if "mysql" in url:
            return "mysql"
        if "postgresql" in url:
            return "postgresql"
        return "sqlite"

    def _get_mysql_credentials(self) -> dict:
        """Extract MySQL connection details from SQLAlchemy engine URL."""
        url = self.db_engine.url
        return {
            "host": url.host or "127.0.0.1",
            "port": url.port or 3306,
            "user": url.username or "root",
            "password": url.password or "",
            "database": url.database or "wgdashboard",
        }

    def _heavy_ignore_args(self, database: str, table_names: list) -> list:
        """mysqldump --ignore-table args for append-only traffic/history tables.

        The ``*_transfer`` and ``*_history_endpoint`` tables are large,
        append-only, and already captured once in the shared transfer dump.
        Including them in every full snapshot bloated each snapshot to ~500 MB,
        which tripped the storage cap and made scheduled backups vanish.
        """
        return [
            f"--ignore-table={database}.{t}"
            for t in table_names
            if t.endswith("_transfer") or t.endswith("_history_endpoint")
        ]

    def _full_db_backup(self, dest_path: str) -> bool:
        """Create a full database dump (non-blocking).

        For MySQL/MariaDB: uses mysqldump --single-transaction (no locks),
        excluding append-only traffic/history tables (kept in the shared
        transfer dump) so the snapshot stays small.
        For SQLite: uses sqlite3.backup() API
        """
        import subprocess
        db_type = self._get_db_type()

        try:
            if db_type == "mysql":
                creds = self._get_mysql_credentials()
                try:
                    with self.db_engine.connect() as conn:
                        rows = conn.execute(text(
                            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                            f"WHERE TABLE_SCHEMA = '{creds['database']}'"
                        ))
                        all_tables = [r[0] for r in rows]
                except Exception:
                    all_tables = []
                ignore_args = self._heavy_ignore_args(creds["database"], all_tables)
                cmd = [
                    "mysqldump",
                    f"--host={creds['host']}",
                    f"--port={creds['port']}",
                    f"--user={creds['user']}",
                    f"--password={creds['password']}",
                    "--single-transaction",
                    "--routines",
                    "--triggers",
                ] + ignore_args + [
                    creds["database"],
                ]
                with open(dest_path, "w") as f:
                    result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=120)
                return result.returncode == 0

            elif db_type == "sqlite":
                import sqlite3
                db_url = str(self.db_engine.url)
                db_path = db_url.split("///")[-1] if "///" in db_url else db_url.split("//")[-1]
                if not os.path.isfile(db_path):
                    return False
                src_conn = sqlite3.connect(db_path)
                dst_conn = sqlite3.connect(dest_path)
                src_conn.backup(dst_conn)
                dst_conn.close()
                src_conn.close()
                return True

            return False
        except Exception:
            return False

    def _full_db_restore(self, src_path: str) -> bool:
        """Restore a full database from dump file.

        For MySQL/MariaDB: uses mysql client to import SQL dump
        For SQLite: uses sqlite3.backup() in reverse
        """
        import subprocess
        db_type = self._get_db_type()

        try:
            if db_type == "mysql":
                creds = self._get_mysql_credentials()
                cmd = [
                    "mysql",
                    f"--host={creds['host']}",
                    f"--port={creds['port']}",
                    f"--user={creds['user']}",
                    f"--password={creds['password']}",
                    creds["database"],
                ]
                with open(src_path, "r") as f:
                    result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, timeout=120)
                return result.returncode == 0

            elif db_type == "sqlite":
                import sqlite3
                db_url = str(self.db_engine.url)
                db_path = db_url.split("///")[-1] if "///" in db_url else db_url.split("//")[-1]
                self.db_engine.dispose()
                src_conn = sqlite3.connect(src_path)
                dst_conn = sqlite3.connect(db_path)
                src_conn.backup(dst_conn)
                dst_conn.close()
                src_conn.close()
                return True

            return False
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
                        qt = self._quote_id(table_name)
                        rows = conn.execute(text(f'SELECT * FROM {qt}'))
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

    def effectiveStorageCapBytes(
        self, max_storage_mb, free_fraction: float = 0.6, free_bytes: Optional[int] = None
    ) -> int:
        """Disk-aware storage cap in bytes: the smaller of the configured MB and
        a fraction of free disk. Keeps the local backup tier from ever eating
        the disk regardless of the configured value (replaces the bare 500 MB)."""
        try:
            configured = int(float(max_storage_mb) * 1024 * 1024)
        except (TypeError, ValueError):
            configured = 500 * 1024 * 1024
        if free_bytes is None:
            try:
                free_bytes = shutil.disk_usage(self.backup_path).free
            except OSError:
                return configured
        return min(configured, int(free_bytes * free_fraction))

    def cleanupOrphans(self, grace_seconds: float = 3600) -> int:
        """Remove global/per-config backup dirs that lack a valid manifest.json
        and are older than grace_seconds (so in-progress writes are never
        touched). Fixes leftovers from failed/half-deleted snapshots. Returns
        the number of directories removed."""
        removed = 0
        now = time.time()
        roots = [os.path.join(self.backup_path, "global")]
        perconfig = os.path.join(self.backup_path, "per-config")
        if os.path.isdir(perconfig):
            for cfg in os.scandir(perconfig):
                if cfg.is_dir():
                    roots.append(cfg.path)
        for root in roots:
            if not os.path.isdir(root):
                continue
            for entry in os.scandir(root):
                if not entry.is_dir():
                    continue
                if os.path.isfile(os.path.join(entry.path, "manifest.json")):
                    continue  # valid snapshot
                try:
                    if (now - entry.stat().st_mtime) < grace_seconds:
                        continue  # too fresh — may be an in-progress write
                except OSError:
                    continue
                if self._delete_directory(entry.path):
                    removed += 1
        return removed

    # -----------------------------------------------------------------------
    # Backup event ledger + health (P1 observability)
    # -----------------------------------------------------------------------
    def _ledger_path(self) -> str:
        return os.path.join(self.backup_path, "backup_events.json")

    def _record_event(self, scope: str, trigger: str, status: str,
                      name: Optional[str] = None, size: Optional[int] = None,
                      error=None) -> None:
        """Append a backup event to the durable ledger (ring buffer, best-effort).
        The ledger is the restart-surviving source of truth for backup health."""
        ev = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "scope": scope, "trigger": trigger, "status": status,
            "name": name, "size": size,
            "error": (str(error)[:500] if error else None),
        }
        try:
            path = self._ledger_path()
            events = []
            if os.path.isfile(path):
                try:
                    with open(path) as f:
                        events = json.load(f)
                    if not isinstance(events, list):
                        events = []
                except (ValueError, OSError):
                    events = []
            events.append(ev)
            events = events[-200:]
            os.makedirs(self.backup_path, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(events, f)
            os.replace(tmp, path)
        except OSError:
            pass  # never break a backup over the ledger

    def readEvents(self, limit: Optional[int] = None) -> list:
        """Return ledger events newest-first."""
        path = self._ledger_path()
        if not os.path.isfile(path):
            return []
        try:
            with open(path) as f:
                events = json.load(f)
            if not isinstance(events, list):
                return []
        except (ValueError, OSError):
            return []
        events = list(reversed(events))
        return events[:limit] if limit else events

    def _read_offhost_status(self, path: Optional[str]) -> dict:
        """Parse the off-host (PBS) status marker 'OK <ts>' / 'FAILED <ts>'."""
        out = {"status": "unknown", "timestamp": None}
        try:
            if path and os.path.isfile(path):
                parts = open(path).read().split()
                if parts:
                    out["status"] = parts[0]
                    if len(parts) > 1:
                        out["timestamp"] = parts[1]
        except OSError:
            pass
        return out

    def health(self, now=None, offhost_status_path: Optional[str] = None) -> dict:
        """Read-model of backup health for the UI / monitoring."""
        events = self.readEvents()

        def _last_success(scope):
            for e in events:
                if e.get("scope") == scope and e.get("status") == "success":
                    return e.get("ts")
            return None

        last_global = _last_success("global")
        if last_global is None:
            # Ledger may post-date existing snapshots; fall back to the newest
            # snapshot on disk so a fresh ledger doesn't read as a false 'red'.
            snaps = self.getGlobalSnapshots()
            if snaps:
                last_global = snaps[0].get("date")
        last_perconfig = _last_success("per-config")
        consecutive = 0
        for e in events:
            if e.get("status") == "failure":
                consecutive += 1
            elif e.get("status") == "success":
                break
        last_failure = next((e.get("ts") for e in events if e.get("status") == "failure"), None)
        try:
            disk_free = shutil.disk_usage(self.backup_path).free
        except OSError:
            disk_free = None
        off = self._read_offhost_status(
            offhost_status_path or "/var/lib/wg-dashboard-pbs/last-status")
        if consecutive >= 3 or last_global is None:
            status = "red"
        elif off.get("status") == "FAILED":
            status = "amber"
        else:
            status = "green"
        return {
            "status": status,
            "last_global_success": last_global,
            "last_perconfig_success": last_perconfig,
            "last_failure": last_failure,
            "consecutive_failures": consecutive,
            "disk_free": disk_free,
            "local_total_size": self._get_dir_size(self.backup_path),
            "off_host": off,
            "events_tail": events[:10],
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
