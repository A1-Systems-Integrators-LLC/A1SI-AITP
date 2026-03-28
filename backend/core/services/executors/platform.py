"""Platform task executors: autonomous check, PDF report, DB backup, DB maintenance, workflow."""

import logging
from typing import Any

from core.services.executors._types import ProgressCallback

logger = logging.getLogger("scheduler")


def _run_autonomous_check(params: dict, progress_cb: ProgressCallback) -> dict:
    """Hourly subsystem health check and auto-remediation."""
    try:
        from core.management.commands.autonomous_check import (
            _check_data_freshness,
            _check_freqtrade,
            _check_ml_training,
            _check_order_health,
            _check_scheduler,
            _check_signal_attributions,
            _fix_ml_training,
        )

        progress_cb(0.1, "Running health checks...")
        checks = [
            _check_freqtrade(),
            _check_ml_training(),
            _check_signal_attributions(),
            _check_data_freshness(),
            _check_scheduler(),
            _check_order_health(),
        ]
        progress_cb(0.7, "Checking for fixes...")

        fixes: list[str] = []
        if params.get("fix", False):
            ml_fix = _fix_ml_training()
            if ml_fix:
                fixes.append(ml_fix)

        issues = [c for c in checks if c["status"] != "pass"]
        progress_cb(1.0, f"Done: {len(issues)} issues found")

        return {
            "status": "completed",
            "all_pass": len(issues) == 0,
            "checks": len(checks),
            "issues": len(issues),
            "fixes_applied": fixes,
        }
    except Exception as e:
        logger.error("Autonomous check failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_pdf_report(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Generate daily PDF intelligence report."""
    progress_cb(0.1, "Generating PDF report")
    try:
        from market.services.pdf_report import PDFReportGenerator

        path = PDFReportGenerator.generate(
            portfolio_id=params.get("portfolio_id", 1),
            lookback_days=params.get("lookback_days", 30),
        )
        progress_cb(0.9, "PDF report generated")

        try:
            from core.services.notification import NotificationService

            NotificationService.send_telegram_sync(
                f"<b>Daily PDF Report Generated</b>\n"
                f"File: {path.name}\n"
                f"Size: {path.stat().st_size / 1024:.1f} KB",
            )
        except Exception:
            logger.debug("PDF report Telegram notification failed", exc_info=True)

        return {"status": "completed", "path": str(path), "size_kb": path.stat().st_size / 1024}
    except Exception as e:
        logger.error("PDF report generation failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_db_backup(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run automated SQLite database backup."""
    import shutil
    import subprocess
    from pathlib import Path as PathLib

    progress_cb(0.1, "Starting database backup")
    try:
        from django.conf import settings as django_settings

        db_path = django_settings.DATABASES["default"]["NAME"]
        backup_dir = PathLib(db_path).parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"a1si_aitp_{timestamp}.db"

        # Use SQLite .backup command for atomic copy
        result = subprocess.run(
            ["sqlite3", str(db_path), f".backup '{backup_path}'"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return {"status": "error", "error": f"sqlite3 backup failed: {result.stderr}"}

        progress_cb(0.5, "Compressing backup")

        # Compress
        import gzip

        gz_path = PathLib(f"{backup_path}.gz")
        with open(backup_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        backup_path.unlink()

        progress_cb(0.8, "Applying GFS retention policy")

        # GFS (Grandfather-Father-Son) retention: 7 daily, 4 weekly, 12 monthly
        from datetime import datetime, timedelta

        now = datetime.now()
        all_backups = sorted(backup_dir.glob("a1si_aitp_*.db.gz"), reverse=True)
        keep = set()

        # Keep 7 most recent (daily)
        for b in all_backups[:7]:
            keep.add(b)

        # Keep 1 per week for last 4 weeks
        for weeks_ago in range(1, 5):
            cutoff = now - timedelta(weeks=weeks_ago)
            for b in all_backups:
                try:
                    ts = b.stem.replace("a1si_aitp_", "").replace(".db", "")
                    btime = datetime.strptime(ts, "%Y%m%d_%H%M%S")
                    if btime <= cutoff:
                        keep.add(b)
                        break
                except ValueError:
                    continue

        # Keep 1 per month for last 12 months
        for months_ago in range(1, 13):
            year = now.year if now.month > months_ago else now.year - 1
            month = now.month - months_ago if now.month > months_ago else 12 + now.month - months_ago
            for b in all_backups:
                try:
                    ts = b.stem.replace("a1si_aitp_", "").replace(".db", "")
                    btime = datetime.strptime(ts, "%Y%m%d_%H%M%S")
                    if btime.year == year and btime.month == month:
                        keep.add(b)
                        break
                except ValueError:
                    continue

        removed = 0
        for b in all_backups:
            if b not in keep:
                b.unlink()
                removed += 1

        size_kb = gz_path.stat().st_size / 1024
        progress_cb(0.9, f"Backup complete: {gz_path.name} ({size_kb:.0f} KB)")

        try:
            from core.services.notification import NotificationService

            NotificationService.send_telegram_sync(
                f"<b>Database Backup Complete</b>\n"
                f"File: {gz_path.name}\n"
                f"Size: {size_kb:.1f} KB\n"
                f"Retained: {len(keep)} backups (GFS: 7d/4w/12m)\n"
                f"Removed: {removed} old backups",
            )
        except Exception:
            pass

        return {
            "status": "completed",
            "path": str(gz_path),
            "size_kb": round(size_kb, 1),
            "retained": len(keep),
            "removed": removed,
        }
    except Exception as e:
        logger.error("Database backup failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_db_maintenance(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run SQLite maintenance: integrity check and optimize.

    No WAL checkpoint needed — using DELETE journal mode (not WAL)
    because WAL is incompatible with Docker virtiofs bind mounts.
    """
    from django.db import connection

    progress_cb(0.1, "Running integrity check")
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
    progress_cb(0.9, "Maintenance complete")
    return {"status": "completed", "integrity": result, "journal_mode": mode}


def _run_workflow(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Execute a workflow pipeline."""
    from analysis.services.workflow_engine import execute_workflow

    return execute_workflow(params, progress_cb)
