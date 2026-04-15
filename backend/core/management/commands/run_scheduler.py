"""Management command to run the task scheduler as a standalone process.

This separates the scheduler from Daphne so background tasks (data pipeline,
ML training, regime detection, etc.) don't compete with the web server for
the GIL. The scheduler process has its own thread pool and can saturate CPU
without blocking HTTP/WebSocket requests.

Usage:
    python manage.py run_scheduler
"""

import signal
import sys
import threading

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the APScheduler task scheduler as a standalone process"

    def handle(self, *args, **options):
        from core.services.scheduler import get_scheduler

        scheduler = get_scheduler()

        self.stdout.write("Starting scheduler worker (standalone)...")
        scheduler.start()

        if not scheduler.running:
            self.stderr.write(self.style.ERROR("Scheduler failed to start"))
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS("Scheduler running. Press Ctrl+C to stop."))

        # Block main thread until SIGINT/SIGTERM
        stop_event = threading.Event()

        def _shutdown(signum, frame):
            self.stdout.write(f"\nReceived signal {signum}, shutting down...")
            scheduler.shutdown()
            stop_event.set()

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        stop_event.wait()
        self.stdout.write(self.style.SUCCESS("Scheduler stopped."))
