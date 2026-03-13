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


def _maybe_start_order_sync() -> None:
    """Start the order sync loop if there are active live orders."""
    try:
        from trading.models import Order, OrderStatus

        has_active = Order.objects.filter(
            mode="live",
            status__in=[
                OrderStatus.SUBMITTED,
                OrderStatus.OPEN,
                OrderStatus.PARTIAL_FILL,
            ],
        ).exists()

        if not has_active:
            return

        import asyncio

        from trading.services.order_sync import start_order_sync

        # In ASGI context there may already be a running loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(start_order_sync())
        except RuntimeError:
            # No running loop (WSGI) — start in a new loop via thread
            import threading

            def _run() -> None:
                asyncio.run(start_order_sync())

            threading.Thread(target=_run, daemon=True).start()

        logger.info("Order sync auto-started on startup (active live orders found)")
    except Exception:
        logger.exception("Failed to auto-start order sync")


def _start_scheduler() -> None:
    """Start the task scheduler if enabled and not in test mode."""
    try:
        from core.services.scheduler import get_scheduler

        scheduler = get_scheduler()
        scheduler.start()
    except Exception:
        logger.exception("Failed to start TaskScheduler")

    _maybe_start_order_sync()


def _verify_scheduler() -> None:
    """Verify scheduler started successfully. If not, retry once."""
    try:
        from core.services.scheduler import get_scheduler

        scheduler = get_scheduler()
        if not scheduler.running:
            logger.error("SCHEDULER NOT RUNNING — retrying startup")
            try:
                scheduler.start()
                if scheduler.running:
                    logger.info("Scheduler started on retry")
                else:
                    logger.critical(
                        "SCHEDULER FAILED TO START — scheduled tasks will not execute"
                    )
            except Exception:
                logger.critical("SCHEDULER RETRY FAILED", exc_info=True)
    except Exception:
        logger.critical("SCHEDULER VERIFICATION FAILED", exc_info=True)


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
        ):
            # Pre-import APScheduler in the main thread during Django startup.
            # Python 3.12's concurrent.futures.process registers an atexit
            # handler at import time — this fails with RuntimeError if the
            # import first happens inside a Timer thread.
            try:
                import apscheduler.schedulers.background  # noqa: F401
            except Exception:
                pass

            if os.environ.get("RUN_MAIN", "true") == "true":
                threading.Timer(2.0, _start_scheduler).start()
                threading.Timer(12.0, _verify_scheduler).start()
