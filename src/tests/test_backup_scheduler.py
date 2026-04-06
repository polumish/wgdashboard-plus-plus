"""
Tests for BackupScheduler — debounce logic, per-config independence, stop().
"""

import os
import sys
import time
from unittest.mock import MagicMock, call

import pytest

# ---------------------------------------------------------------------------
# Module import helper
# ---------------------------------------------------------------------------

def _import_scheduler():
    src = os.path.join(os.path.dirname(__file__), "..")
    if src not in sys.path:
        sys.path.insert(0, src)
    from modules.BackupScheduler import BackupScheduler
    return BackupScheduler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_backup_manager():
    """A BackupManager mock that accepts any keyword arguments."""
    bm = MagicMock()
    bm.createConfigBackup.return_value = {"status": True, "name": "wg0_test"}
    bm.enforcePerConfigRotation.return_value = None
    bm.createGlobalSnapshot.return_value = {"status": True, "name": "snapshot_test"}
    bm.enforceRotation.return_value = None
    return bm


@pytest.fixture()
def mock_config():
    """A DashboardConfig mock that returns falsy values for all keys by default."""
    cfg = MagicMock()
    cfg.GetConfig.return_value = None
    return cfg


@pytest.fixture()
def scheduler(mock_backup_manager, mock_config):
    """A BackupScheduler instance with fast debounce times for testing."""
    BackupScheduler = _import_scheduler()
    sched = BackupScheduler(mock_backup_manager, mock_config)
    sched._debounce_seconds = 0.1
    sched._max_wait_seconds = 5.0
    return sched


# ---------------------------------------------------------------------------
# TestBackupScheduler
# ---------------------------------------------------------------------------

class TestBackupScheduler:

    def test_debounce_coalesces_rapid_events(self, scheduler, mock_backup_manager):
        """Five rapid events for the same config should produce at most two backups."""
        for i in range(5):
            scheduler.onPeerChange.__func__  # ensure method exists
            # Bypass the "enabled" check by calling _debounce_backup directly
            scheduler._debounce_backup("wg0", "event", f"peer_{i}")

        # Wait for debounce to fire
        time.sleep(0.5)

        call_count = mock_backup_manager.createConfigBackup.call_count
        # Allow 1 or 2: 1 ideal, 2 possible if max-wait fires simultaneously
        assert call_count >= 1, "Expected at least one backup"
        assert call_count <= 2, f"Expected at most 2 backups (got {call_count})"

    def test_debounce_per_config_independent(self, scheduler, mock_backup_manager):
        """Events for wg0 and wg1 should each trigger their own backup."""
        scheduler._debounce_backup("wg0", "event", "added: peer_a")
        scheduler._debounce_backup("wg1", "event", "added: peer_b")

        # Wait for both debounce timers
        time.sleep(0.5)

        calls = mock_backup_manager.createConfigBackup.call_args_list
        config_names = [c.kwargs.get("config_name") or c.args[0] for c in calls]

        assert "wg0" in config_names, "wg0 should have been backed up"
        assert "wg1" in config_names, "wg1 should have been backed up"

    def test_scheduler_stop(self, scheduler):
        """Calling stop() should set _running to False and cancel all timers."""
        # Queue some timers before stopping
        scheduler._debounce_backup("wg0", "event", "some change")
        scheduler._debounce_backup("wg1", "event", "another change")

        scheduler.stop()

        assert scheduler._running is False
        # Timers should have been cleared
        assert len(scheduler._debounce_timers) == 0
        assert len(scheduler._max_wait_timers) == 0

    def test_on_peer_change_respects_disabled_flag(self, scheduler, mock_backup_manager, mock_config):
        """onPeerChange should do nothing when auto_backup_peer_changes is disabled."""
        mock_config.GetConfig.return_value = "false"

        scheduler.onPeerChange("wg0", "added", "some_peer")
        time.sleep(0.3)

        mock_backup_manager.createConfigBackup.assert_not_called()

    def test_on_peer_change_triggers_backup_when_enabled(self, scheduler, mock_backup_manager, mock_config):
        """onPeerChange should queue a backup when auto_backup_peer_changes is enabled."""
        mock_config.GetConfig.return_value = "true"

        scheduler.onPeerChange("wg0", "added", "some_peer")
        time.sleep(0.5)

        mock_backup_manager.createConfigBackup.assert_called_once()
        call_kwargs = mock_backup_manager.createConfigBackup.call_args
        # Accept both positional and keyword argument styles
        config_arg = call_kwargs.kwargs.get("config_name") or call_kwargs.args[0]
        assert config_arg == "wg0"

    def test_on_config_change_respects_disabled_flag(self, scheduler, mock_backup_manager, mock_config):
        """onConfigChange should do nothing when auto_backup_config_changes is disabled."""
        mock_config.GetConfig.return_value = None

        scheduler.onConfigChange("wg0", "MTU changed")
        time.sleep(0.3)

        mock_backup_manager.createConfigBackup.assert_not_called()

    def test_on_config_change_triggers_backup_when_enabled(self, scheduler, mock_backup_manager, mock_config):
        """onConfigChange should queue a backup when auto_backup_config_changes is enabled."""
        mock_config.GetConfig.return_value = "true"

        scheduler.onConfigChange("wg0", "DNS changed")
        time.sleep(0.5)

        mock_backup_manager.createConfigBackup.assert_called_once()

    def test_enforce_per_config_rotation_called_after_backup(self, scheduler, mock_backup_manager, mock_config):
        """After each debounced backup, enforcePerConfigRotation should be called."""
        mock_config.GetConfig.return_value = None  # keep default = 10

        scheduler._debounce_backup("wg0", "event", "change")
        time.sleep(0.5)

        mock_backup_manager.enforcePerConfigRotation.assert_called_once()

    def test_start_returns_thread(self, mock_backup_manager, mock_config):
        """start() should return a running daemon thread."""
        import threading
        BackupScheduler = _import_scheduler()
        sched = BackupScheduler(mock_backup_manager, mock_config)
        t = sched.start()
        try:
            assert isinstance(t, threading.Thread)
            assert t.is_alive()
        finally:
            sched.stop()
