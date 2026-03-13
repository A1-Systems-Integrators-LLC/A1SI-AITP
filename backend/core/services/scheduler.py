"""TaskScheduler — APScheduler-based background task execution.

Starts in CoreConfig.ready(), syncs SCHEDULED_TASKS from settings to DB,
delegates work to JobRunner for BackgroundJob tracking.
"""

import atexit
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from django.conf import settings

logger = logging.getLogger("scheduler")

_scheduler_instance: "TaskScheduler | None" = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> "TaskScheduler":
    """Return the singleton TaskScheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        with _scheduler_lock:
            if _scheduler_instance is None:
                _scheduler_instance = TaskScheduler()
    return _scheduler_instance


class TaskScheduler:
    """Manages APScheduler BackgroundScheduler lifecycle and task execution."""

    def __init__(self) -> None:
        self._scheduler = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Sync tasks from settings → DB, add APScheduler interval jobs, start."""
        if self._running:
            return

        from apscheduler.schedulers.background import BackgroundScheduler

        # Recover any jobs/workflows left in running/pending state from a previous crash
        try:
            from analysis.services.job_runner import (
                recover_stale_jobs,
                recover_stale_workflow_runs,
            )

            recover_stale_jobs()
            recover_stale_workflow_runs()
        except Exception:
            logger.exception("Failed to recover stale jobs on startup")

        self._scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1},
            timezone="UTC",
        )

        self._sync_tasks_to_db()
        self._sync_workflows_to_db()
        self._scheduler.start()
        self._schedule_active_tasks()
        self._running = True

        # Register shutdown — if atexit fails, scheduler is already running
        try:
            atexit.register(self.shutdown)
        except RuntimeError:
            logger.warning("atexit registration failed — shutdown must be called manually")

        logger.info("TaskScheduler started with %d tasks", self._active_task_count())

        # Bootstrap: run ML training if no models exist (deferred to avoid
        # ThreadPoolExecutor shutdown race during early startup)
        def _ml_bootstrap() -> None:
            try:
                from core.platform_bridge import ensure_platform_imports

                ensure_platform_imports()
                from common.ml.registry import ModelRegistry

                registry = ModelRegistry()
                if not registry.list_models():
                    logger.info("No ML models found — triggering initial training")
                    self.trigger_task("ml_training")
            except Exception:
                logger.warning("ML bootstrap check failed", exc_info=True)

        threading.Timer(5.0, _ml_bootstrap).start()

        # Validate watchlist symbols against exchange in background
        threading.Thread(
            target=self._validate_watchlist, daemon=True, name="watchlist-validator"
        ).start()

    def shutdown(self) -> None:
        """Gracefully stop the scheduler."""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("TaskScheduler shut down")

    def _sync_tasks_to_db(self) -> None:
        """Ensure SCHEDULED_TASKS from settings are reflected in DB."""
        from core.models import ScheduledTask

        configured_tasks: dict[str, dict[str, Any]] = getattr(settings, "SCHEDULED_TASKS", {})
        for task_id, cfg in configured_tasks.items():
            ScheduledTask.objects.update_or_create(
                id=task_id,
                defaults={
                    "name": cfg["name"],
                    "description": cfg.get("description", ""),
                    "task_type": cfg["task_type"],
                    "interval_seconds": cfg.get("interval_seconds"),
                    "params": cfg.get("params", {}),
                },
            )

    def _sync_workflows_to_db(self) -> None:
        """Ensure WORKFLOW_TEMPLATES from settings are reflected in DB."""
        from analysis.models import Workflow, WorkflowStep

        templates: dict[str, dict[str, Any]] = getattr(settings, "WORKFLOW_TEMPLATES", {})
        for wf_id, cfg in templates.items():
            wf, created = Workflow.objects.update_or_create(
                id=wf_id,
                defaults={
                    "name": cfg["name"],
                    "description": cfg.get("description", ""),
                    "asset_class": cfg.get("asset_class", "crypto"),
                    "is_template": True,
                    "schedule_enabled": cfg.get("schedule_enabled", False),
                    "schedule_interval_seconds": cfg.get("schedule_interval_seconds"),
                },
            )
            if created:
                for step_data in cfg.get("steps", []):
                    WorkflowStep.objects.create(workflow=wf, **step_data)

    def _schedule_active_tasks(self) -> None:
        """Add APScheduler jobs for all active tasks and enabled workflows."""
        from core.models import ScheduledTask

        for task in ScheduledTask.objects.filter(status=ScheduledTask.ACTIVE):
            if task.interval_seconds and task.interval_seconds > 0:
                self._scheduler.add_job(
                    self._execute_task,
                    "interval",
                    seconds=task.interval_seconds,
                    id=task.id,
                    args=[task.id],
                    replace_existing=True,
                )
                # Update next_run_at from APScheduler
                job = self._scheduler.get_job(task.id)
                nrt = getattr(job, "next_run_time", None) if job else None
                if nrt:
                    ScheduledTask.objects.filter(id=task.id).update(
                        next_run_at=nrt,
                    )

        # Schedule enabled workflows
        from analysis.models import Workflow

        for wf in Workflow.objects.filter(schedule_enabled=True, is_active=True):
            if wf.schedule_interval_seconds and wf.schedule_interval_seconds > 0:
                job_id = f"workflow_{wf.id}"
                self._scheduler.add_job(
                    self._execute_workflow,
                    "interval",
                    seconds=wf.schedule_interval_seconds,
                    id=job_id,
                    args=[wf.id],
                    replace_existing=True,
                )
                apjob = self._scheduler.get_job(job_id)
                nrt = getattr(apjob, "next_run_time", None) if apjob else None
                logger.info(
                    "Scheduled workflow %s (%s) every %ds, next: %s",
                    wf.name, wf.id, wf.schedule_interval_seconds, nrt,
                )

    def _active_task_count(self) -> int:
        from core.models import ScheduledTask

        return ScheduledTask.objects.filter(status=ScheduledTask.ACTIVE).count()

    def _validate_watchlist(self) -> None:
        """Validate watchlist symbols against the exchange on startup.

        Logs ERROR for each symbol that doesn't exist on the configured exchange.
        Runs in a background thread to avoid blocking scheduler startup.
        """
        try:
            from core.platform_bridge import ensure_platform_imports, get_platform_config

            ensure_platform_imports()
            config = get_platform_config()
            if not config:
                return  # Already logged by get_platform_config

            data_cfg = config.get("data", {})
            watchlists = {
                "crypto": data_cfg.get("watchlist", []),
                "equity": data_cfg.get("equity_watchlist", []),
                "forex": data_cfg.get("forex_watchlist", []),
            }

            # Only validate crypto watchlist against exchange — equity/forex use yfinance
            crypto_symbols = watchlists.get("crypto", [])
            if not crypto_symbols:
                return

            import ccxt

            exchange_cfg = config.get("exchanges", {}).get("kraken", {})
            exchange_id = exchange_cfg.get("exchange_id", "kraken")
            exchange = getattr(ccxt, exchange_id)()
            exchange.load_markets()

            invalid = [s for s in crypto_symbols if s not in exchange.markets]
            if invalid:
                logger.error(
                    "WATCHLIST VALIDATION: %d/%d crypto symbols NOT found on %s: %s",
                    len(invalid),
                    len(crypto_symbols),
                    exchange_id,
                    ", ".join(invalid),
                )
            else:
                logger.info(
                    "Watchlist validation passed: all %d crypto symbols exist on %s",
                    len(crypto_symbols),
                    exchange_id,
                )
        except Exception:
            logger.exception("Watchlist validation failed")

    def _execute_task(self, task_id: str) -> None:
        """Execute a scheduled task via JobRunner."""
        from core.models import ScheduledTask
        from core.services.task_registry import TASK_REGISTRY

        try:
            task = ScheduledTask.objects.get(id=task_id)
        except ScheduledTask.DoesNotExist:
            logger.error("Scheduled task %s not found", task_id)
            return

        if task.status != ScheduledTask.ACTIVE:
            return

        executor = TASK_REGISTRY.get(task.task_type)
        if not executor:
            logger.error("No executor for task_type=%s (task=%s)", task.task_type, task_id)
            return

        # Submit via JobRunner for BackgroundJob tracking
        from analysis.services.job_runner import get_job_runner

        job_type = f"scheduled_{task.task_type}"
        job_id = get_job_runner().submit(job_type, executor, task.params)

        now = datetime.now(tz=timezone.utc)
        update_fields = {
            "last_run_at": now,
            "last_run_status": "submitted",
            "last_run_job_id": job_id,
            "run_count": task.run_count + 1,
        }

        # Update next_run_at from APScheduler
        if self._scheduler:
            apjob = self._scheduler.get_job(task_id)
            nrt = getattr(apjob, "next_run_time", None) if apjob else None
            if nrt:
                update_fields["next_run_at"] = nrt

        ScheduledTask.objects.filter(id=task_id).update(**update_fields)
        logger.info("Task %s submitted as job %s", task_id, job_id)

        # Broadcast scheduler event
        try:
            from core.services.ws_broadcast import broadcast_scheduler_event

            broadcast_scheduler_event(
                task_id=task_id,
                task_name=task.name,
                task_type=task.task_type,
                status="submitted",
                job_id=job_id,
                message=f"Task {task.name} submitted",
            )
        except Exception:
            pass

    def pause_task(self, task_id: str) -> bool:
        """Pause a scheduled task."""
        from core.models import ScheduledTask

        try:
            task = ScheduledTask.objects.get(id=task_id)
        except ScheduledTask.DoesNotExist:
            return False

        task.status = ScheduledTask.PAUSED
        task.next_run_at = None
        task.save(update_fields=["status", "next_run_at", "updated_at"])

        if self._scheduler:
            import contextlib

            with contextlib.suppress(Exception):
                self._scheduler.remove_job(task_id)

        logger.info("Task %s paused", task_id)

        try:
            from core.services.ws_broadcast import broadcast_scheduler_event

            broadcast_scheduler_event(
                task_id=task_id,
                task_name=task.name,
                task_type=task.task_type,
                status="paused",
                message=f"Task {task.name} paused",
            )
        except Exception:
            pass

        return True

    def resume_task(self, task_id: str) -> bool:
        """Resume a paused task."""
        from core.models import ScheduledTask

        try:
            task = ScheduledTask.objects.get(id=task_id)
        except ScheduledTask.DoesNotExist:
            return False

        task.status = ScheduledTask.ACTIVE
        task.save(update_fields=["status", "updated_at"])

        if self._scheduler and task.interval_seconds and task.interval_seconds > 0:
            self._scheduler.add_job(
                self._execute_task,
                "interval",
                seconds=task.interval_seconds,
                id=task_id,
                args=[task_id],
                replace_existing=True,
            )
            apjob = self._scheduler.get_job(task_id)
            nrt = getattr(apjob, "next_run_time", None) if apjob else None
            if nrt:
                ScheduledTask.objects.filter(id=task_id).update(
                    next_run_at=nrt,
                )

        logger.info("Task %s resumed", task_id)

        try:
            from core.services.ws_broadcast import broadcast_scheduler_event

            broadcast_scheduler_event(
                task_id=task_id,
                task_name=task.name,
                task_type=task.task_type,
                status="resumed",
                message=f"Task {task.name} resumed",
            )
        except Exception:
            pass

        return True

    def trigger_task(self, task_id: str) -> str | None:
        """Trigger immediate execution of a task. Returns job_id or None."""
        from core.models import ScheduledTask
        from core.services.task_registry import TASK_REGISTRY

        try:
            task = ScheduledTask.objects.get(id=task_id)
        except ScheduledTask.DoesNotExist:
            return None

        executor = TASK_REGISTRY.get(task.task_type)
        if not executor:
            return None

        from analysis.services.job_runner import get_job_runner

        job_type = f"scheduled_{task.task_type}"
        job_id = get_job_runner().submit(job_type, executor, task.params)

        now = datetime.now(tz=timezone.utc)
        ScheduledTask.objects.filter(id=task_id).update(
            last_run_at=now,
            last_run_status="triggered",
            last_run_job_id=job_id,
            run_count=task.run_count + 1,
        )

        logger.info("Task %s manually triggered as job %s", task_id, job_id)

        try:
            from core.services.ws_broadcast import broadcast_scheduler_event

            broadcast_scheduler_event(
                task_id=task_id,
                task_name=task.name,
                task_type=task.task_type,
                status="triggered",
                job_id=job_id,
                message=f"Task {task.name} manually triggered",
            )
        except Exception:
            pass

        return job_id

    def _execute_workflow(self, workflow_id: str) -> None:
        """Execute a scheduled workflow via WorkflowEngine."""
        from analysis.models import Workflow

        try:
            wf = Workflow.objects.get(id=workflow_id)
        except Workflow.DoesNotExist:
            logger.error("Scheduled workflow %s not found", workflow_id)
            return

        if not wf.schedule_enabled or not wf.is_active:
            return

        try:
            from analysis.services.workflow_engine import WorkflowEngine

            run_id, job_id = WorkflowEngine.trigger(
                workflow_id=workflow_id,
                trigger="scheduled",
                params=wf.params,
            )
            logger.info("Workflow %s triggered as job %s (run %s)", wf.name, job_id, run_id)

            wf.last_run_at = datetime.now(tz=timezone.utc)
            wf.save(update_fields=["last_run_at"])

            try:
                from core.services.ws_broadcast import broadcast_scheduler_event

                broadcast_scheduler_event(
                    task_id=f"workflow_{workflow_id}",
                    task_name=wf.name,
                    task_type="workflow",
                    status="triggered",
                    job_id=job_id,
                    message=f"Workflow {wf.name} auto-triggered",
                )
            except Exception:
                pass
        except Exception as e:
            logger.error("Scheduled workflow %s failed: %s", workflow_id, e, exc_info=True)

    def get_status(self) -> dict[str, Any]:
        """Return scheduler status summary."""
        from core.models import ScheduledTask

        total = ScheduledTask.objects.count()
        active = ScheduledTask.objects.filter(status=ScheduledTask.ACTIVE).count()
        paused = ScheduledTask.objects.filter(status=ScheduledTask.PAUSED).count()

        return {
            "running": self._running,
            "total_tasks": total,
            "active_tasks": active,
            "paused_tasks": paused,
        }
