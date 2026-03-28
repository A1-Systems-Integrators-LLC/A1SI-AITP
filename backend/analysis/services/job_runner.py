"""Job runner — dispatches sync functions to a thread pool, tracks progress in-memory,
and persists job state to DB via Django ORM.
"""

import concurrent.futures
import logging
import math
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from django.conf import settings

# ── Job timeout configuration ─────────────────────────────────────────
JOB_TIMEOUT_SECONDS = 3600  # 1 hour default

JOB_TIMEOUT_OVERRIDES: dict[str, int] = {
    "vbt_screen": 7200,
    "nautilus_backtest": 7200,
    "ml_training": 7200,
    "freqtrade_backtest": 7200,
    "hft_backtest": 7200,
}

logger = logging.getLogger("job_runner")


def _sanitize_for_json(obj: Any) -> Any:
    """Convert numpy/pandas types and NaN/Inf to JSON-safe Python types."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    # numpy scalar types
    type_name = type(obj).__module__
    if type_name == "numpy":
        try:
            if hasattr(obj, "item"):
                val = obj.item()
                if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    return None
                return val
        except (ValueError, OverflowError):
            return str(obj)
    return obj


def recover_stale_jobs() -> int:
    """Mark all running/pending BackgroundJobs as failed on startup.

    Returns the number of recovered jobs.
    """
    from analysis.models import BackgroundJob

    now = datetime.now(timezone.utc)
    count = BackgroundJob.objects.filter(
        status__in=["running", "pending"],
    ).update(
        status="failed",
        error="Interrupted by server restart",
        completed_at=now,
    )
    if count:
        logger.info("Recovered %d stale BackgroundJob(s) on startup", count)
    return count


def recover_stale_workflow_runs() -> int:
    """Mark all running/pending WorkflowRuns as failed on startup.

    Returns the number of recovered runs.
    """
    from analysis.models import WorkflowRun

    now = datetime.now(timezone.utc)
    count = WorkflowRun.objects.filter(
        status__in=["running", "pending"],
    ).update(
        status="failed",
        error="Interrupted by server restart",
        completed_at=now,
    )
    if count:
        logger.info("Recovered %d stale WorkflowRun(s) on startup", count)
    return count


# In-memory progress store for live polling
_job_progress: dict[str, dict[str, Any]] = {}

# Singleton runner instance
_runner_instance = None


def get_job_runner() -> "JobRunner":
    global _runner_instance
    if _runner_instance is None:
        _runner_instance = JobRunner(max_workers=settings.MAX_JOB_WORKERS)
    return _runner_instance


# Critical tasks that must never be starved by long-running batch compute
CRITICAL_TASK_TYPES = frozenset(
    {
        "risk_monitoring",
        "order_sync",
        "strategy_orchestration",
        "regime_detection",
        "market_scan",
        "forex_paper_trading",
    }
)

# Retry configuration for failed tasks
MAX_RETRIES = 3
RETRY_BASE_DELAY_S = 5  # Exponential backoff: 5s, 10s, 20s
# Tasks re-scheduled frequently enough that retrying is wasteful
NO_RETRY_TYPES = CRITICAL_TASK_TYPES | frozenset({"data_quality_check", "autonomous_check"})


class JobRunner:
    def __init__(self, max_workers: int = 2):
        # Batch pool for compute-heavy tasks (VBT screens, backtests, ML training)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        # Critical pool for safety-sensitive tasks (risk, order sync, orchestration)
        self._critical_executor = ThreadPoolExecutor(
            max_workers=max(2, max_workers),
            thread_name_prefix="critical",
        )

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
            id=job_id,
            job_type=job_type,
            status="pending",
            params=params,
        )
        _job_progress[job_id] = {"progress": 0.0, "progress_message": "Queued"}
        # Route critical tasks to a dedicated pool so they're never blocked
        pool = self._critical_executor if job_type in CRITICAL_TASK_TYPES else self._executor
        pool.submit(self._run_job, job_id, run_fn, params or {})
        return job_id

    def _run_job(self, job_id: str, run_fn: Callable, params: dict) -> None:
        import django

        django.setup()
        from analysis.models import BackgroundJob

        try:
            job_obj = BackgroundJob.objects.get(id=job_id)
            BackgroundJob.objects.filter(id=job_id).update(
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            _job_progress[job_id] = {"progress": 0.0, "progress_message": "Running"}

            # Broadcast job start
            try:
                from core.services.ws_broadcast import broadcast_scheduler_event

                broadcast_scheduler_event(
                    task_id="",
                    task_name=job_obj.job_type,
                    task_type=job_obj.job_type,
                    status="running",
                    job_id=job_id,
                    message=f"Job {job_id[:8]} started",
                )
            except Exception:
                logger.debug("WS broadcast failed for job %s start", job_id[:8], exc_info=True)

            _last_persisted_pct = [0]  # mutable container for closure

            def progress_callback(progress: float, message: str = "") -> None:
                clamped = min(progress, 1.0)
                _job_progress[job_id] = {
                    "progress": clamped,
                    "progress_message": message,
                }
                # Persist to DB every 10% increment
                pct_10 = int(clamped * 10)
                if pct_10 > _last_persisted_pct[0]:
                    _last_persisted_pct[0] = pct_10
                    BackgroundJob.objects.filter(id=job_id).update(
                        progress=clamped,
                        progress_message=message[:200],
                    )

            # ── Execute with retry on hard failures ─────────────────────
            timeout = JOB_TIMEOUT_OVERRIDES.get(job_obj.job_type, JOB_TIMEOUT_SECONDS)
            max_attempts = 1 if job_obj.job_type in NO_RETRY_TYPES else MAX_RETRIES + 1
            last_err: Exception | None = None
            result = None

            for attempt in range(max_attempts):
                if attempt > 0:
                    delay = RETRY_BASE_DELAY_S * (2 ** (attempt - 1))
                    logger.warning(
                        "Job %s retry %d/%d in %ds",
                        job_id[:8], attempt, MAX_RETRIES, delay,
                    )
                    _job_progress[job_id] = {
                        "progress": 0.0,
                        "progress_message": f"Retrying ({attempt}/{MAX_RETRIES})...",
                    }
                    time.sleep(delay)
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as timeout_pool:
                        future = timeout_pool.submit(run_fn, params, progress_callback)
                        try:
                            result = future.result(timeout=timeout)
                        except concurrent.futures.TimeoutError as te:
                            raise TimeoutError(
                                f"Job timed out after {timeout}s"
                            ) from te
                    last_err = None
                    break
                except Exception as retry_exc:
                    last_err = retry_exc
                    logger.warning(
                        "Job %s attempt %d failed: %s",
                        job_id[:8], attempt + 1, retry_exc,
                    )

            if last_err is not None:
                raise last_err

            # Detect soft failures: executor returned {"status": "error"}
            is_soft_failure = isinstance(result, dict) and result.get("status") == "error"
            final_status = "failed" if is_soft_failure else "completed"

            _job_progress[job_id] = {"progress": 1.0, "progress_message": "Complete"}
            job = BackgroundJob.objects.get(id=job_id)
            job.status = final_status
            job.progress = 1.0
            job.result = _sanitize_for_json(result)
            if is_soft_failure:
                job.error = result.get("error", "Task returned error status")
            job.completed_at = datetime.now(timezone.utc)
            job.save()

            # Alert on critical task failures via Telegram
            if is_soft_failure and job.job_type in CRITICAL_TASK_TYPES:
                try:
                    from core.services.notification import NotificationService

                    msg = (
                        f"<b>CRITICAL TASK FAILED</b>\n"
                        f"Task: {job.job_type}\n"
                        f"Error: {job.error}\n"
                        f"Job: {job_id[:8]}"
                    )
                    NotificationService.send_telegram_sync(msg)
                except Exception:
                    logger.warning("Failed to send Telegram alert for %s", job.job_type)

            # Broadcast job completion
            try:
                from core.services.ws_broadcast import broadcast_scheduler_event

                broadcast_scheduler_event(
                    task_id="",
                    task_name=job.job_type,
                    task_type=job.job_type,
                    status="completed",
                    job_id=job_id,
                    message=f"Job {job_id[:8]} completed",
                )
            except Exception:
                logger.debug("WS broadcast failed for job %s completion", job_id[:8], exc_info=True)

            # Persist structured result for backtest jobs
            backtest_job_types = {
                "backtest",
                "scheduled_nautilus_backtest",
                "scheduled_hft_backtest",
            }
            if job.job_type in backtest_job_types and isinstance(result, dict):
                from analysis.models import BacktestResult

                if result.get("results") and result.get("status") == "completed":
                    # Multi-strategy result (nautilus/hft executors)
                    for sub in result["results"]:
                        if sub.get("status") == "completed" and sub.get("result"):
                            sub_result = sub["result"]
                            BacktestResult.objects.create(
                                job=job,
                                framework=result.get("framework", ""),
                                asset_class=result.get("asset_class", "crypto"),
                                strategy_name=sub.get("strategy", ""),
                                symbol=sub.get("symbol", ""),
                                timeframe=sub_result.get("timeframe", params.get("timeframe", "")),
                                metrics=sub_result.get("metrics"),
                                trades=sub_result.get("trades"),
                                config=params,
                            )
                elif "error" not in result:
                    # Flat result (direct backtest job)
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
            # Persist ScreenResult for VBT screen jobs
            screen_job_types = {"scheduled_vbt_screen"}
            if job.job_type in screen_job_types and isinstance(result, dict):
                from analysis.models import ScreenResult

                if result.get("results") and result.get("status") == "completed":
                    asset_class = params.get("asset_class", "crypto")
                    for sub in result["results"]:
                        if sub.get("status") == "completed" and sub.get("result"):
                            sub_result = sub["result"]
                            symbol = sub.get("symbol", sub_result.get("symbol", ""))
                            timeframe = sub_result.get("timeframe", params.get("timeframe", ""))
                            strategies = sub_result.get("strategies", {})
                            for strategy_name, strat_data in strategies.items():
                                if "error" in strat_data:
                                    continue
                                try:
                                    ScreenResult.objects.create(
                                        job=job,
                                        symbol=symbol,
                                        asset_class=asset_class,
                                        timeframe=timeframe,
                                        strategy_name=strategy_name,
                                        top_results=_sanitize_for_json(
                                            strat_data.get("top_results")
                                        ),
                                        summary=_sanitize_for_json(strat_data.get("summary")),
                                        total_combinations=strat_data.get("total_combinations", 0),
                                    )
                                except Exception:
                                    logger.warning(
                                        "Failed to persist ScreenResult for %s/%s",
                                        symbol,
                                        strategy_name,
                                        exc_info=True,
                                    )

        except Exception as e:
            logger.exception(f"Job {job_id} failed: {e}")
            _job_progress[job_id] = {"progress": 0.0, "progress_message": f"Failed: {e}"}
            BackgroundJob.objects.filter(id=job_id).update(
                status="failed",
                error=str(e),
                completed_at=datetime.now(timezone.utc),
            )
            # Broadcast job failure
            try:
                from core.services.ws_broadcast import broadcast_scheduler_event

                broadcast_scheduler_event(
                    task_id="",
                    task_name=params.get("job_type", "unknown"),
                    task_type=params.get("job_type", "unknown"),
                    status="failed",
                    job_id=job_id,
                    message=f"Job {job_id[:8]} failed: {e}",
                )
            except Exception:
                logger.debug("WS broadcast failed for job %s failure", job_id[:8], exc_info=True)

    @staticmethod
    def get_live_progress(job_id: str) -> dict[str, Any] | None:
        return _job_progress.get(job_id)

    @staticmethod
    def cancel_job(job_id: str) -> bool:
        from analysis.models import BackgroundJob

        updated = BackgroundJob.objects.filter(
            id=job_id,
            status__in=["pending", "running"],
        ).update(status="cancelled", completed_at=datetime.now(timezone.utc))
        return updated > 0
