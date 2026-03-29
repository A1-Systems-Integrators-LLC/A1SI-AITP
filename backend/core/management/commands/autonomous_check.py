"""Autonomous system health check — verify and remediate subsystem issues.

Designed to run hourly as a scheduled task. Checks:
1. Freqtrade instances — are all enabled instances running?
2. ML training — has it run at least once?
3. Signal attributions — is the feedback loop recording?
4. Data freshness — is market data being refreshed?
5. Scheduler — is it running?

Usage:
    manage.py autonomous_check          # Report only
    manage.py autonomous_check --fix    # Auto-remediate
    manage.py autonomous_check --json   # JSON output
"""

import json
import sys
from datetime import timedelta
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

CheckResult = dict[str, Any]


def _check_freqtrade() -> CheckResult:
    """Verify all enabled Freqtrade instances are running."""
    ft_instances = getattr(settings, "FREQTRADE_INSTANCES", [])
    results: list[dict] = []
    all_ok = True

    for cfg in ft_instances:
        name = cfg.get("name", "unknown")
        port = cfg.get("port", 0)
        enabled = cfg.get("enabled", False)
        if not enabled:
            results.append({"name": name, "status": "disabled"})
            continue

        running = False
        try:
            r = requests.get(
                f"http://localhost:{port}/api/v1/ping",
                auth=(cfg.get("username", ""), cfg.get("password", "")),
                timeout=3,
            )
            running = r.status_code == 200
        except Exception:
            pass

        status = "running" if running else "down"
        if not running:
            all_ok = False
        results.append({"name": name, "port": port, "status": status})

    return {
        "name": "Freqtrade Instances",
        "status": "pass" if all_ok else "fail",
        "instances": results,
    }


def _check_ml_training() -> CheckResult:
    """Verify ML training has run at least once."""
    from analysis.models import BackgroundJob

    completed = BackgroundJob.objects.filter(
        job_type__contains="ml_training",
        status="completed",
    ).count()

    if completed > 0:
        last = BackgroundJob.objects.filter(
            job_type__contains="ml_training",
            status="completed",
        ).order_by("-completed_at").first()
        return {
            "name": "ML Training",
            "status": "pass",
            "completed_runs": completed,
            "last_run": last.completed_at.isoformat() if last and last.completed_at else None,
        }

    return {
        "name": "ML Training",
        "status": "fail",
        "completed_runs": 0,
        "detail": "ML training has never completed successfully",
    }


def _check_signal_attributions() -> CheckResult:
    """Check if signal attributions are being recorded."""
    from analysis.models import MLPrediction, SignalAttribution

    predictions_24h = MLPrediction.objects.filter(
        predicted_at__gte=timezone.now() - timedelta(hours=24),
    ).count()
    attributions_total = SignalAttribution.objects.count()
    attributions_24h = SignalAttribution.objects.filter(
        recorded_at__gte=timezone.now() - timedelta(hours=24),
    ).count()

    status = "pass" if attributions_total > 0 else "fail"
    return {
        "name": "Signal Attributions",
        "status": status,
        "total": attributions_total,
        "last_24h": attributions_24h,
        "predictions_24h": predictions_24h,
        "detail": "No attributions recorded (feedback loop disconnected)" if attributions_total == 0 else None,
    }


def _check_data_freshness() -> CheckResult:
    """Check if market data is being refreshed."""
    from core.models import ScheduledTask

    task = ScheduledTask.objects.filter(id="data_refresh_crypto").first()
    if not task or not task.last_run_at:
        return {"name": "Data Freshness", "status": "fail", "detail": "data_refresh_crypto never ran"}

    age = timezone.now() - task.last_run_at
    age_minutes = age.total_seconds() / 60

    status = "pass" if age_minutes < 60 else "warn" if age_minutes < 240 else "fail"
    return {
        "name": "Data Freshness",
        "status": status,
        "last_refresh_minutes_ago": round(age_minutes, 1),
        "last_run": task.last_run_at.isoformat(),
    }


def _check_scheduler() -> CheckResult:
    """Check if the APScheduler is running."""
    try:
        from core.services.scheduler import get_scheduler

        scheduler = get_scheduler()
        running = scheduler.running
        return {
            "name": "Scheduler",
            "status": "pass" if running else "fail",
            "running": running,
        }
    except Exception as e:
        return {"name": "Scheduler", "status": "fail", "detail": str(e)}


def _check_order_health() -> CheckResult:
    """Check for excessive order rejections."""
    from trading.models import Order, OrderStatus

    total = Order.objects.count()
    rejected = Order.objects.filter(status=OrderStatus.REJECTED).count()
    filled = Order.objects.filter(status=OrderStatus.FILLED).count()
    rejection_rate = (rejected / total * 100) if total > 0 else 0

    status = "pass" if rejection_rate < 50 else "warn" if rejection_rate < 80 else "fail"
    return {
        "name": "Order Health",
        "status": status,
        "total_orders": total,
        "filled": filled,
        "rejected": rejected,
        "rejection_rate": round(rejection_rate, 1),
    }


def _fix_ml_training() -> str | None:
    """Trigger ML training if it has never run."""
    from analysis.models import BackgroundJob

    if BackgroundJob.objects.filter(job_type__contains="ml_training", status="completed").exists():
        return None

    try:
        from core.services.scheduler import get_scheduler

        scheduler = get_scheduler()
        job_id = scheduler.trigger_task("ml_training")
        if job_id:
            return f"Triggered ML training (job {job_id})"
    except Exception:
        pass
    return None


class Command(BaseCommand):
    help = "Autonomous system health check — verify subsystem status and auto-remediate"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--fix", action="store_true", help="Auto-remediate detected issues")
        parser.add_argument("--json", action="store_true", help="JSON output")

    def handle(self, *args: Any, **options: Any) -> None:
        is_json = options["json"]
        fix = options["fix"]

        checks = [
            _check_freqtrade(),
            _check_ml_training(),
            _check_signal_attributions(),
            _check_data_freshness(),
            _check_scheduler(),
            _check_order_health(),
        ]

        fixes: list[str] = []
        if fix:
            # Auto-fix: trigger ML training if needed
            ml_fix = _fix_ml_training()
            if ml_fix:
                fixes.append(ml_fix)

        issues = [c for c in checks if c["status"] != "pass"]
        all_pass = len(issues) == 0

        result = {
            "timestamp": timezone.now().isoformat(),
            "all_pass": all_pass,
            "checks": checks,
            "issues_count": len(issues),
            "fixes_applied": fixes,
        }

        if is_json:
            self.stdout.write(json.dumps(result, indent=2, default=str))
        else:
            self.stdout.write(f"\n{'=' * 50}")
            self.stdout.write("  AUTONOMOUS SYSTEM CHECK")
            self.stdout.write(f"{'=' * 50}\n")

            for check in checks:
                icon = "\u2713" if check["status"] == "pass" else "\u2717" if check["status"] == "fail" else "!"
                self.stdout.write(f"  [{icon}] {check['name']}: {check['status']}")
                detail = check.get("detail")
                if detail:
                    self.stdout.write(f"      {detail}")

            self.stdout.write("")
            if fixes:
                self.stdout.write("  Fixes applied:")
                for f in fixes:
                    self.stdout.write(f"    - {f}")

            self.stdout.write(f"\n  Result: {'ALL PASS' if all_pass else f'{len(issues)} ISSUES FOUND'}")
            self.stdout.write(f"{'=' * 50}\n")

        if not all_pass:
            sys.exit(1)
