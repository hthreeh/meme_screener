"""
Task scheduler module for DEX Price Monitor.
Manages periodic execution of monitoring tasks.
"""

import logging
import sys
from typing import Callable, Optional

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler

from config.settings import AppSettings
from services.notifier import NotificationService


class TaskScheduler:
    """
    Scheduler for periodic monitoring tasks.

    Wraps APScheduler to provide clean interface for
    scheduling and error handling.
    """

    def __init__(self, settings: AppSettings,
                 notifier: Optional[NotificationService] = None):
        """
        Initialize scheduler.

        Args:
            settings: Application configuration
            notifier: Notification service for error alerts
        """
        self.settings = settings
        self.notifier = notifier
        self._logger = logging.getLogger(__name__)

        # Use Beijing timezone
        self.timezone = pytz.timezone('Asia/Shanghai')
        self._scheduler: Optional[BlockingScheduler] = None
        self._task_func: Optional[Callable] = None

    def register_task(self, task_func: Callable) -> None:
        """
        Register the main task function.

        Args:
            task_func: Callable to execute on each interval
        """
        self._task_func = task_func

    def start(self, run_immediately: bool = True) -> None:
        """
        Start the scheduler.

        Args:
            run_immediately: If True, run task once before starting schedule
        """
        if self._task_func is None:
            raise RuntimeError("No task registered. Call register_task() first.")

        # Run immediately if requested
        if run_immediately:
            self._logger.info("Running initial task...")
            try:
                self._task_func()
            except Exception as e:
                self._logger.error(f"Initial task failed: {e}", exc_info=True)

        # Create and start scheduler
        self._scheduler = BlockingScheduler(timezone=self.timezone)
        self._scheduler.add_job(
            self._safe_task,
            'interval',
            minutes=self.settings.task_interval_minutes
        )

        self._logger.info(
            f"Scheduler started. Tasks will run every "
            f"{self.settings.task_interval_minutes} minutes."
        )

        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self._logger.info("Scheduler stopped by user")
        except Exception as e:
            self._handle_fatal_error(e)

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._logger.info("Scheduler stopped")

    def _safe_task(self) -> None:
        """Wrapper for task with error handling."""
        try:
            if self._task_func:
                self._task_func()
        except Exception as e:
            self._logger.error(f"Task execution failed: {e}", exc_info=True)
            # Don't stop scheduler for individual task failures

    def _handle_fatal_error(self, error: Exception) -> None:
        """
        Handle fatal scheduler errors.

        Sends notification and exits program.
        """
        error_msg = f"Scheduler encountered fatal error: {error}"
        self._logger.critical(error_msg, exc_info=True)

        if self.notifier:
            try:
                self.notifier.send_error_notification(
                    error_msg,
                    "【致命错误】DEX监控程序停止"
                )
            except Exception:
                pass

        sys.exit(1)
