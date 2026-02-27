import logging
import os
import threading

from django.apps import AppConfig
from django.conf import settings
from django.db.backends.signals import connection_created

logger = logging.getLogger("scheduler")


def _set_sqlite_pragmas(sender, connection, **kwargs):
    """Enable WAL mode and tune SQLite for performance."""
    if connection.vendor == "sqlite":
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")


def _start_scheduler() -> None:
    """Start the task scheduler if enabled and not in test mode."""
    try:
        from core.services.scheduler import get_scheduler

        scheduler = get_scheduler()
        scheduler.start()
    except Exception:
        logger.exception("Failed to start TaskScheduler")


class CoreConfig(AppConfig):
    name = "core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        connection_created.connect(_set_sqlite_pragmas)

        # Start scheduler once per process.
        # RUN_MAIN is only set by Django's autoreload (runserver).
        # Under Daphne/gunicorn/Docker, it's never set — so we also start
        # when RUN_MAIN is absent (i.e., single-process ASGI server).
        # Deferred via timer so DB is fully ready (avoids "database during
        # app initialization" warning).
        if (
            getattr(settings, "SCHEDULER_ENABLED", False)
            and not getattr(settings, "TESTING", False)
            and os.environ.get("RUN_MAIN", "true") == "true"
        ):
            threading.Timer(2.0, _start_scheduler).start()
