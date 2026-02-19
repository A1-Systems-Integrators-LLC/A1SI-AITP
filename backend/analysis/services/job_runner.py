"""
Job runner — dispatches sync functions to a thread pool, tracks progress in-memory,
and persists job state to DB via Django ORM.
"""

import logging
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from django.conf import settings

logger = logging.getLogger("job_runner")

# In-memory progress store for live polling
_job_progress: dict[str, dict[str, Any]] = {}

# Singleton runner instance
_runner_instance = None


def get_job_runner() -> "JobRunner":
    global _runner_instance
    if _runner_instance is None:
        _runner_instance = JobRunner(max_workers=settings.MAX_JOB_WORKERS)
    return _runner_instance


class JobRunner:
    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")

    def submit(
        self,
        job_type: str,
        run_fn: Callable[..., Any],
        params: dict | None = None,
    ) -> str:
        """Create a DB job record and dispatch run_fn to the thread pool."""
        import django

        django.setup()
        from analysis.models import BackgroundJob

        job_id = str(uuid.uuid4())
        BackgroundJob.objects.create(
            id=job_id, job_type=job_type, status="pending", params=params,
        )
        _job_progress[job_id] = {"progress": 0.0, "progress_message": "Queued"}
        self._executor.submit(self._run_job, job_id, run_fn, params or {})
        return job_id

    def _run_job(self, job_id: str, run_fn: Callable, params: dict) -> None:
        import django

        django.setup()
        from analysis.models import BackgroundJob

        try:
            BackgroundJob.objects.filter(id=job_id).update(
                status="running", started_at=datetime.now(timezone.utc),
            )
            _job_progress[job_id] = {"progress": 0.0, "progress_message": "Running"}

            def progress_callback(progress: float, message: str = "") -> None:
                _job_progress[job_id] = {
                    "progress": min(progress, 1.0),
                    "progress_message": message,
                }

            result = run_fn(params, progress_callback)

            _job_progress[job_id] = {"progress": 1.0, "progress_message": "Complete"}
            job = BackgroundJob.objects.get(id=job_id)
            job.status = "completed"
            job.progress = 1.0
            job.result = result
            job.completed_at = datetime.now(timezone.utc)
            job.save()

            # Persist structured result for backtest jobs
            if job.job_type == "backtest" and isinstance(result, dict) and "error" not in result:
                from analysis.models import BacktestResult

                BacktestResult.objects.create(
                    job=job,
                    framework=result.get("framework", params.get("framework", "")),
                    strategy_name=result.get("strategy", params.get("strategy", "")),
                    symbol=result.get("symbol", params.get("symbol", "")),
                    timeframe=result.get("timeframe", params.get("timeframe", "")),
                    timerange=params.get("timerange", ""),
                    metrics=result.get("metrics"),
                    trades=result.get("trades"),
                    config=params,
                )
        except Exception as e:
            logger.exception(f"Job {job_id} failed: {e}")
            _job_progress[job_id] = {"progress": 0.0, "progress_message": f"Failed: {e}"}
            BackgroundJob.objects.filter(id=job_id).update(
                status="failed", error=str(e),
                completed_at=datetime.now(timezone.utc),
            )

    @staticmethod
    def get_live_progress(job_id: str) -> dict[str, Any] | None:
        return _job_progress.get(job_id)

    @staticmethod
    def cancel_job(job_id: str) -> bool:
        from analysis.models import BackgroundJob

        updated = BackgroundJob.objects.filter(
            id=job_id, status__in=["pending", "running"],
        ).update(status="cancelled", completed_at=datetime.now(timezone.utc))
        return updated > 0
