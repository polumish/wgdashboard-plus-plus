"""
Tests for BackupManager — global snapshots, per-config backups,
delete/download, and integrity verification.
"""
import json
import os
import shutil
import tarfile
from unittest.mock import MagicMock, patch
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine_mock(tables=None):
    """Return a SQLAlchemy engine mock that yields configurable table data."""
    if tables is None:
        tables = {}

    engine = MagicMock()
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = conn

    def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.keys.return_value = ["id", "value"]
        result.__iter__ = MagicMock(return_value=iter([]))
        return result

    conn.execute.side_effect = _execute

    # inspect mock
    inspector = MagicMock()
    inspector.get_table_names.return_value = list(tables.keys())
    return engine, inspector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def backup_env(tmp_path):
    """Isolated environment: fake wg/awg conf dirs, ini, mock db engine."""
    wg_path = tmp_path / "wg"
    awg_path = tmp_path / "awg"
    backup_path = tmp_path / "backups"
    wg_path.mkdir()
    awg_path.mkdir()
    backup_path.mkdir()

    # Create fake .conf files
    (wg_path / "wg0.conf").write_text("[Interface]\nAddress = 10.0.0.1/24\n")
    (wg_path / "wg1.conf").write_text("[Interface]\nAddress = 10.0.1.1/24\n")
    (awg_path / "awg0.conf").write_text("[Interface]\nAddress = 10.1.0.1/24\n")

    # Fake ini
    ini_path = tmp_path / "wg-dashboard.ini"
    ini_path.write_text("[Server]\napp_port = 10086\n")

    engine, inspector = _make_engine_mock()

    return {
        "wg_path": str(wg_path),
        "awg_path": str(awg_path),
        "backup_path": str(backup_path),
        "ini_path": str(ini_path),
        "engine": engine,
        "inspector": inspector,
        "tmp_path": tmp_path,
    }


def _make_manager(env, inspector=None):
    """Import and instantiate BackupManager with the given env."""
    import sys
    src = os.path.join(os.path.dirname(__file__), "..")
    if src not in sys.path:
        sys.path.insert(0, src)

    from modules.BackupManager import BackupManager

    mgr = BackupManager(
        backup_path=env["backup_path"],
        wg_conf_path=env["wg_path"],
        awg_conf_path=env["awg_path"],
        ini_path=env["ini_path"],
        db_engine=env["engine"],
    )
    # Patch inspect so DB export doesn't fail
    insp = inspector or env["inspector"]
    with patch("modules.BackupManager.inspect", return_value=insp):
        pass  # just confirm it's importable; actual patch per test
    return mgr


# ---------------------------------------------------------------------------
# TestBackupManagerGlobalSnapshots
# ---------------------------------------------------------------------------

class TestBackupManagerGlobalSnapshots:

    def test_create_global_snapshot_creates_directory(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createGlobalSnapshot(trigger="manual")

        assert result["status"] is True
        snap_dir = os.path.join(backup_env["backup_path"], "global", result["name"])
        assert os.path.isdir(snap_dir)

    def test_create_global_snapshot_has_manifest(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createGlobalSnapshot(trigger="manual")

        manifest_path = os.path.join(
            backup_env["backup_path"], "global", result["name"], "manifest.json"
        )
        assert os.path.isfile(manifest_path)
        manifest = json.loads(open(manifest_path).read())

        assert "version" in manifest
        assert "app_version" in manifest
        assert manifest["type"] == "global"
        assert manifest["trigger"] == "manual"
        assert "timestamp" in manifest
        assert "components" in manifest
        assert "checksums" in manifest
        assert "size_bytes" in manifest

    def test_create_global_snapshot_copies_configs(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createGlobalSnapshot(trigger="manual")

        configs_dir = os.path.join(
            backup_env["backup_path"], "global", result["name"], "configs"
        )
        assert os.path.isdir(configs_dir)
        conf_files = os.listdir(configs_dir)
        assert "wg0.conf" in conf_files
        assert "wg1.conf" in conf_files
        assert "awg0.conf" in conf_files

    def test_create_global_snapshot_copies_ini(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createGlobalSnapshot(trigger="manual")

        ini_backup = os.path.join(
            backup_env["backup_path"], "global", result["name"],
            "settings", "wg-dashboard.ini"
        )
        assert os.path.isfile(ini_backup)

    def test_list_global_snapshots_empty(self, backup_env):
        mgr = _make_manager(backup_env)
        snapshots = mgr.getGlobalSnapshots()
        assert snapshots == []

    def test_list_global_snapshots_returns_created(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            r1 = mgr.createGlobalSnapshot(trigger="manual")
            r2 = mgr.createGlobalSnapshot(trigger="scheduled")

        snapshots = mgr.getGlobalSnapshots()
        assert len(snapshots) == 2
        # Newest first
        names = [s["name"] for s in snapshots]
        assert names[0] == r2["name"]
        assert names[1] == r1["name"]

    def test_list_global_snapshots_filter_by_type(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            mgr.createGlobalSnapshot(trigger="manual")
            mgr.createGlobalSnapshot(trigger="scheduled")

        manual = mgr.getGlobalSnapshots(filter_type="manual")
        assert len(manual) == 1
        assert manual[0]["trigger"] == "manual"

        scheduled = mgr.getGlobalSnapshots(filter_type="scheduled")
        assert len(scheduled) == 1
        assert scheduled[0]["trigger"] == "scheduled"


# ---------------------------------------------------------------------------
# TestBackupManagerDeleteDownload
# ---------------------------------------------------------------------------

class TestBackupManagerDeleteDownload:

    def test_delete_global_snapshot(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createGlobalSnapshot(trigger="manual")

        name = result["name"]
        snap_dir = os.path.join(backup_env["backup_path"], "global", name)
        assert os.path.isdir(snap_dir)

        deleted = mgr.deleteGlobalSnapshot(name)
        assert deleted is True
        assert not os.path.exists(snap_dir)

    def test_delete_nonexistent_snapshot(self, backup_env):
        mgr = _make_manager(backup_env)
        deleted = mgr.deleteGlobalSnapshot("nonexistent_snapshot_name")
        assert deleted is False

    def test_download_global_snapshot(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createGlobalSnapshot(trigger="manual")

        success, tar_path = mgr.downloadGlobalSnapshot(result["name"])
        assert success is True
        assert tar_path.endswith(".tar.gz")
        assert os.path.isfile(tar_path)
        # Verify it's a valid tar archive
        assert tarfile.is_tarfile(tar_path)

    def test_verify_integrity_valid(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createGlobalSnapshot(trigger="manual")

        snap_dir = os.path.join(backup_env["backup_path"], "global", result["name"])
        assert mgr.verifyIntegrity(snap_dir) is True

    def test_verify_integrity_corrupted(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createGlobalSnapshot(trigger="manual")

        snap_dir = os.path.join(backup_env["backup_path"], "global", result["name"])

        # Corrupt a config file
        conf_files = [
            f for f in os.listdir(os.path.join(snap_dir, "configs"))
        ]
        corrupt_file = os.path.join(snap_dir, "configs", conf_files[0])
        with open(corrupt_file, "a") as f:
            f.write("\nCORRUPTED DATA\n")

        assert mgr.verifyIntegrity(snap_dir) is False


# ---------------------------------------------------------------------------
# TestBackupManagerPerConfig
# ---------------------------------------------------------------------------

class TestBackupManagerPerConfig:

    def test_create_config_backup(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createConfigBackup("wg0", trigger="manual")

        assert result["status"] is True
        assert "name" in result

    def test_create_config_backup_copies_conf(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createConfigBackup("wg0", trigger="manual")

        backup_dir = os.path.join(
            backup_env["backup_path"], "per-config", "wg0", result["name"]
        )
        assert os.path.isdir(backup_dir)
        assert os.path.isfile(os.path.join(backup_dir, "wg0.conf"))

    def test_list_config_backups(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            r1 = mgr.createConfigBackup("wg0", trigger="manual")
            r2 = mgr.createConfigBackup("wg0", trigger="peer_change")

        backups = mgr.getConfigBackups("wg0")
        assert len(backups) == 2
        # Newest first
        assert backups[0]["name"] == r2["name"]
        assert backups[1]["name"] == r1["name"]

    def test_list_config_backups_empty(self, backup_env):
        mgr = _make_manager(backup_env)
        backups = mgr.getConfigBackups("wg0")
        assert backups == []

    def test_delete_config_backup(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createConfigBackup("wg0", trigger="manual")

        name = result["name"]
        deleted = mgr.deleteConfigBackup("wg0", name)
        assert deleted is True

        backup_dir = os.path.join(
            backup_env["backup_path"], "per-config", "wg0", name
        )
        assert not os.path.exists(backup_dir)

    def test_config_backup_nonexistent_config(self, backup_env):
        mgr = _make_manager(backup_env)
        with patch("modules.BackupManager.inspect", return_value=backup_env["inspector"]):
            result = mgr.createConfigBackup("nonexistent_config", trigger="manual")

        assert result["status"] is False
