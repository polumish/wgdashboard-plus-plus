"""
BackupMigration — one-time migration of legacy WGDashboard backups.

Legacy backups are stored as:
  <wg_conf_path>/WGDashboard_Backup/<config_name>_<YYYYMMDDHHMMSS>.conf
  <wg_conf_path>/WGDashboard_Backup/<config_name>_<YYYYMMDDHHMMSS>.sql  (optional)

This module converts them to the modern per-config backup format used by
BackupManager.
"""

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone

MANIFEST_VERSION = "1"
LEGACY_BACKUP_PATTERN = re.compile(r"^(.+)_(\d{14})\.conf$")
MARKER_FILENAME = ".legacy_migrated"


def migrate_legacy_backups(
    wg_conf_path: str,
    awg_conf_path: str,
    backup_path: str,
) -> dict:
    """Migrate legacy WGDashboard backups to the modern format.

    Scans ``<wg_conf_path>/WGDashboard_Backup/`` and
    ``<awg_conf_path>/WGDashboard_Backup/`` for legacy backup files and
    converts each one to a per-config backup directory understood by
    BackupManager.

    A marker file ``<backup_path>/.legacy_migrated`` is written after a
    successful run so the migration is never repeated.

    Parameters
    ----------
    wg_conf_path:
        Directory containing WireGuard ``.conf`` files (and potentially
        a ``WGDashboard_Backup/`` sub-directory).
    awg_conf_path:
        Directory containing AmneziaWG ``.conf`` files (same structure).
    backup_path:
        Root of the modern backup tree (the same value passed to
        BackupManager).

    Returns
    -------
    dict
        ``{"status": True, "count": N}``  — migration completed (or was
        previously completed; count = 0 in that case).
        ``{"status": False, "error": "..."}``  — unexpected failure.
    """
    marker_path = os.path.join(backup_path, MARKER_FILENAME)

    # Idempotency guard
    if os.path.isfile(marker_path):
        return {"status": True, "count": 0}

    try:
        count = 0

        for conf_dir in (wg_conf_path, awg_conf_path):
            legacy_dir = os.path.join(conf_dir, "WGDashboard_Backup")
            if not os.path.isdir(legacy_dir):
                continue

            for filename in os.listdir(legacy_dir):
                match = LEGACY_BACKUP_PATTERN.match(filename)
                if match is None:
                    continue

                config_name = match.group(1)
                raw_ts = match.group(2)  # YYYYMMDDHHMMSS

                conf_src = os.path.join(legacy_dir, filename)
                sql_src = os.path.join(legacy_dir, f"{config_name}_{raw_ts}.sql")

                # Build destination directory
                formatted_ts = _format_timestamp(raw_ts)
                backup_name = f"{config_name}_{formatted_ts}"
                backup_dir = os.path.join(
                    backup_path, "per-config", config_name, backup_name
                )
                os.makedirs(backup_dir, exist_ok=True)

                # 1. Copy .conf file
                conf_dest = os.path.join(backup_dir, f"{config_name}.conf")
                shutil.copy2(conf_src, conf_dest)

                # 2. Handle optional .sql file → peers.json
                peers_data: dict = {}
                if os.path.isfile(sql_src):
                    with open(sql_src, "r", errors="replace") as f:
                        sql_content = f.read()
                    peers_data["_legacy_sql"] = sql_content

                peers_path = os.path.join(backup_dir, "peers.json")
                with open(peers_path, "w") as f:
                    json.dump(peers_data, f, indent=2)

                # 3. Build checksums and manifest
                checksums: dict[str, str] = {}
                components: list[str] = []

                for root, _dirs, files in os.walk(backup_dir):
                    for fname in sorted(files):
                        if fname == "manifest.json":
                            continue
                        fpath = os.path.join(root, fname)
                        rel = os.path.relpath(fpath, backup_dir)
                        checksums[rel] = _sha256(fpath)
                        components.append(rel)

                manifest = {
                    "version": MANIFEST_VERSION,
                    "app_version": "legacy",
                    "type": "per-config",
                    "config_name": config_name,
                    "timestamp": _raw_ts_to_iso(raw_ts),
                    "trigger": "legacy_migration",
                    "event_detail": f"Migrated from {filename}",
                    "components": sorted(components),
                    "checksums": checksums,
                    "size_bytes": _dir_size(backup_dir),
                }

                manifest_path = os.path.join(backup_dir, "manifest.json")
                with open(manifest_path, "w") as f:
                    json.dump(manifest, f, indent=2)

                count += 1

            # Remove the old WGDashboard_Backup directory after processing
            try:
                shutil.rmtree(legacy_dir)
            except Exception:  # noqa: BLE001
                pass

        # Write migration marker
        os.makedirs(backup_path, exist_ok=True)
        with open(marker_path, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())

        return {"status": True, "count": count}

    except Exception as exc:  # noqa: BLE001
        return {"status": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _format_timestamp(raw_ts: str) -> str:
    """Convert YYYYMMDDHHMMSS → YYYYMMDD_HHMMSS_000000 (BackupManager style)."""
    # raw_ts is exactly 14 digits: YYYYMMDDHHMMSS
    if len(raw_ts) == 14:
        date_part = raw_ts[:8]   # YYYYMMDD
        time_part = raw_ts[8:]   # HHMMSS
        return f"{date_part}_{time_part}_000000"
    return raw_ts


def _raw_ts_to_iso(raw_ts: str) -> str:
    """Convert YYYYMMDDHHMMSS to an ISO-8601 UTC string."""
    try:
        dt = datetime.strptime(raw_ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return raw_ts


def _sha256(filepath: str) -> str:
    """Return 'sha256:<hexdigest>' for the given file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _dir_size(path: str) -> int:
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
