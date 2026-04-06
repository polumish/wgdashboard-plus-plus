"""
BackupScheduler — drives automatic and event-triggered WGDashboard backups.

Supports:
  - Scheduled backups (daily / weekly / monthly) checked every 60 seconds
  - Event-driven per-config backups with trailing-edge debounce
  - Max-wait cap so a busy config is still backed up eventually
"""

import threading
from datetime import datetime, timezone


class BackupScheduler:
    """Coordinates scheduled and event-triggered backups.

    Parameters
    ----------
    backup_manager:
        A BackupManager instance used to create backups.
    dashboard_config:
        A DashboardConfig instance; must support GetConfig(section, key).
    """

    def __init__(self, backup_manager, dashboard_config):
        self.bm = backup_manager
        self.config = dashboard_config

        self._running = False
        self._lock = threading.Lock()

        # config_name -> threading.Timer (trailing-edge debounce)
        self._debounce_timers: dict[str, threading.Timer] = {}
        # config_name -> threading.Timer (max-wait cap)
        self._max_wait_timers: dict[str, threading.Timer] = {}

        # Overridable for tests
        self._debounce_seconds: float = 30
        self._max_wait_seconds: float = 300

        # type ("daily" | "weekly" | "monthly") -> datetime of last scheduled run
        self._last_scheduled: dict[str, datetime] = {}

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def start(self) -> threading.Thread:
        """Start the background scheduling loop.

        Returns the daemon thread so callers can join() if needed.
        """
        self._running = True
        t = threading.Thread(target=self._schedule_loop, daemon=True, name="BackupScheduler")
        t.start()
        return t

    def stop(self) -> None:
        """Stop the scheduler and cancel all pending timers."""
        self._running = False
        with self._lock:
            for timer in list(self._debounce_timers.values()):
                timer.cancel()
            for timer in list(self._max_wait_timers.values()):
                timer.cancel()
            self._debounce_timers.clear()
            self._max_wait_timers.clear()

    # -----------------------------------------------------------------------
    # Background loop
    # -----------------------------------------------------------------------

    def _schedule_loop(self) -> None:
        """Main loop: check scheduled backups every 60 seconds."""
        while self._running:
            try:
                self._check_scheduled_backups()
            except Exception:  # noqa: BLE001
                pass
            # Sleep in small increments so stop() is responsive
            for _ in range(60):
                if not self._running:
                    return
                threading.Event().wait(1)

    def _check_scheduled_backups(self) -> None:
        """Evaluate daily / weekly / monthly schedules and fire if due."""
        now = datetime.now(timezone.utc)

        # ---- Daily --------------------------------------------------------
        daily_enabled = self._get_config("BackupSchedules", "daily_enabled")
        if daily_enabled in (True, "true", "True", "1", 1):
            daily_time_str = self._get_config("BackupSchedules", "daily_time") or "03:00"
            if self._is_daily_due(now, daily_time_str):
                self._run_scheduled("daily")

        # ---- Weekly -------------------------------------------------------
        weekly_enabled = self._get_config("BackupSchedules", "weekly_enabled")
        if weekly_enabled in (True, "true", "True", "1", 1):
            weekly_day_str = self._get_config("BackupSchedules", "weekly_day") or "0"
            if self._is_weekly_due(now, weekly_day_str):
                self._run_scheduled("weekly")

        # ---- Monthly ------------------------------------------------------
        monthly_enabled = self._get_config("BackupSchedules", "monthly_enabled")
        if monthly_enabled in (True, "true", "True", "1", 1):
            monthly_day_str = self._get_config("BackupSchedules", "monthly_day") or "1"
            if self._is_monthly_due(now, monthly_day_str):
                self._run_scheduled("monthly")

    # -----------------------------------------------------------------------
    # Schedule helpers
    # -----------------------------------------------------------------------

    def _is_daily_due(self, now: datetime, time_str: str) -> bool:
        """Return True if current time is past the target time and no daily backup today."""
        try:
            hour, minute = (int(x) for x in time_str.split(":"))
        except (ValueError, AttributeError):
            return False

        today = now.date()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if now < target:
            return False  # Not yet time today

        last = self._last_scheduled.get("daily")
        if last is not None and last.date() == today:
            return False  # Already ran today

        return True

    def _is_weekly_due(self, now: datetime, day_str: str) -> bool:
        """Return True if today is the configured weekday and no backup this week."""
        try:
            target_weekday = int(day_str)  # 0=Monday … 6=Sunday
        except (ValueError, TypeError):
            return False

        if now.weekday() != target_weekday:
            return False

        last = self._last_scheduled.get("weekly")
        if last is not None:
            # Same ISO week
            if last.isocalendar()[:2] == now.isocalendar()[:2]:
                return False

        return True

    def _is_monthly_due(self, now: datetime, day_str: str) -> bool:
        """Return True if today is the configured day-of-month and no backup this month."""
        try:
            target_day = int(day_str)
        except (ValueError, TypeError):
            return False

        if now.day != target_day:
            return False

        last = self._last_scheduled.get("monthly")
        if last is not None:
            if last.year == now.year and last.month == now.month:
                return False

        return True

    def _run_scheduled(self, sched: str) -> None:
        """Create a global snapshot for the given schedule type and enforce rotation."""
        trigger = f"scheduled_{sched}"
        result = self.bm.createGlobalSnapshot(trigger=trigger)

        if result.get("status"):
            self._last_scheduled[sched] = datetime.now(timezone.utc)

            # Read rotation limits from config
            try:
                daily_keep = int(self._get_config("BackupRotation", "daily_keep") or 7)
            except (ValueError, TypeError):
                daily_keep = 7
            try:
                weekly_keep = int(self._get_config("BackupRotation", "weekly_keep") or 4)
            except (ValueError, TypeError):
                weekly_keep = 4
            try:
                monthly_keep = int(self._get_config("BackupRotation", "monthly_keep") or 3)
            except (ValueError, TypeError):
                monthly_keep = 3
            try:
                max_storage_mb = float(
                    self._get_config("BackupRotation", "max_storage_mb") or 500
                )
            except (ValueError, TypeError):
                max_storage_mb = 500

            self.bm.enforceRotation(
                daily_keep=daily_keep,
                weekly_keep=weekly_keep,
                monthly_keep=monthly_keep,
                max_storage_mb=max_storage_mb,
            )

    # -----------------------------------------------------------------------
    # Event-driven backups
    # -----------------------------------------------------------------------

    def onPeerChange(self, config_name: str, action: str, peer_name: str) -> None:
        """Called when a peer is added, removed or modified.

        Parameters
        ----------
        config_name: WireGuard configuration name (e.g. "wg0")
        action:      short verb, e.g. "added", "removed", "updated"
        peer_name:   peer public key or display name
        """
        enabled = self._get_config("BackupTriggers", "auto_backup_peer_changes")
        if not self._is_truthy(enabled):
            return
        self._debounce_backup(config_name, "event", f"{action}: {peer_name}")

    def onConfigChange(self, config_name: str, change_detail: str) -> None:
        """Called when a configuration's settings change.

        Parameters
        ----------
        config_name:   WireGuard configuration name
        change_detail: human-readable description of what changed
        """
        enabled = self._get_config("BackupTriggers", "auto_backup_config_changes")
        if not self._is_truthy(enabled):
            return
        self._debounce_backup(config_name, "event", change_detail)

    # -----------------------------------------------------------------------
    # Debounce machinery
    # -----------------------------------------------------------------------

    def _debounce_backup(self, config_name: str, trigger: str, event_detail: str) -> None:
        """Schedule a debounced backup for config_name.

        Trailing-edge debounce: each call resets the debounce timer.
        A max-wait timer ensures a backup fires even during continuous activity.
        """
        with self._lock:
            # Cancel existing debounce timer and start a fresh one
            existing = self._debounce_timers.pop(config_name, None)
            if existing is not None:
                existing.cancel()

            debounce_timer = threading.Timer(
                self._debounce_seconds,
                self._execute_debounced_backup,
                args=(config_name, trigger, event_detail),
            )
            debounce_timer.daemon = True
            self._debounce_timers[config_name] = debounce_timer
            debounce_timer.start()

            # Start max-wait timer only if one isn't already running
            if config_name not in self._max_wait_timers:
                max_wait_timer = threading.Timer(
                    self._max_wait_seconds,
                    self._execute_debounced_backup,
                    args=(config_name, trigger, event_detail),
                )
                max_wait_timer.daemon = True
                self._max_wait_timers[config_name] = max_wait_timer
                max_wait_timer.start()

    def _execute_debounced_backup(
        self, config_name: str, trigger: str, event_detail: str
    ) -> None:
        """Execute the actual backup; clean up both timers for this config."""
        with self._lock:
            debounce_timer = self._debounce_timers.pop(config_name, None)
            if debounce_timer is not None:
                debounce_timer.cancel()

            max_wait_timer = self._max_wait_timers.pop(config_name, None)
            if max_wait_timer is not None:
                max_wait_timer.cancel()

        self.bm.createConfigBackup(
            config_name=config_name,
            trigger=trigger,
            event_detail=event_detail,
        )

        try:
            keep = int(
                self._get_config("BackupRotation", "per_config_keep") or 10
            )
        except (ValueError, TypeError):
            keep = 10

        self.bm.enforcePerConfigRotation(config_name=config_name, keep=keep)

    # -----------------------------------------------------------------------
    # Utility helpers
    # -----------------------------------------------------------------------

    def _get_config(self, section: str, key: str):
        """Safe wrapper around dashboard_config.GetConfig()."""
        try:
            return self.config.GetConfig(section, key)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _is_truthy(value) -> bool:
        """Return True for values that represent a enabled/on/true state."""
        return value in (True, "true", "True", "1", 1, "yes", "Yes", "on", "On")
