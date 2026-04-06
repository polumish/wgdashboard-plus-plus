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

        self._lock = threading.Lock()

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
        with self._lock:
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
                all_data = self._export_database()

                peers_data = {
                    k: v for k, v in all_data.items() if k not in DASHBOARD_TABLES
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
        with self._lock:
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

        with self._lock:
            ts = self._timestamp()
            name = f"{config_name}_{ts}"
            backup_dir = os.path.join(
                self.backup_path, "per-config", config_name, name
            )

            try:
                os.makedirs(backup_dir, exist_ok=True)

                # 1. Copy .conf file
                shutil.copy2(conf_file, os.path.join(backup_dir, f"{config_name}.conf"))

                # 2. DB export — only tables for this config
                db_dir = os.path.join(backup_dir)
                all_data = self._export_database()

                # Tables belonging to this config
                config_tables = {
                    tbl: rows
                    for tbl, rows in all_data.items()
                    if tbl == config_name
                    or any(tbl == f"{config_name}{suf}" for suf in CONFIG_TABLE_SUFFIXES[1:])
                }
                # Also include ConfigurationsInfo row for this config
                if "ConfigurationsInfo" in all_data:
                    config_tables["ConfigurationsInfo"] = [
                        row for row in all_data["ConfigurationsInfo"]
                        if row.get("Name") == config_name
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
        with self._lock:
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

    def _export_database(self) -> dict:
        """Export all tables from the database as {table_name: [row_dict, ...]}."""
        result = {}
        try:
            inspector = inspect(self.db_engine)
            table_names = inspector.get_table_names()

            with self.db_engine.connect() as conn:
                for table_name in table_names:
                    try:
                        rows = conn.execute(text(f"SELECT * FROM \"{table_name}\""))
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
                if filter_type is not None and m.get("trigger") != filter_type:
                    continue
                snapshots.append(
                    {
                        "name": entry.name,
                        "timestamp": m.get("timestamp", ""),
                        "trigger": m.get("trigger", ""),
                        "size_bytes": m.get("size_bytes", 0),
                        "components": m.get("components", []),
                    }
                )
            except Exception:  # noqa: BLE001
                continue

        # Newest first — sort by timestamp string (ISO-8601 sorts lexicographically)
        snapshots.sort(key=lambda s: s["timestamp"], reverse=True)
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
