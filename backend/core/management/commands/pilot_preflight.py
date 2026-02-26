"""Pre-flight checklist for the live trading pilot.

Runs 10 readiness checks and reports go/no-go.
Usage: manage.py pilot_preflight [--json] [--portfolio-id N]
"""

import json
import shutil
import sys
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

CheckResult = dict[str, Any]  # {name, status, detail}


def _check_frameworks() -> CheckResult:
    """Check that trading framework tiers are importable."""
    from core.views import _get_framework_status

    frameworks = _get_framework_status()
    # The 4 trading tiers
    tier_names = {"VectorBT", "Freqtrade", "NautilusTrader", "HFT Backtest"}
    tiers = [f for f in frameworks if f["name"] in tier_names]
    installed = [f for f in tiers if f["installed"]]
    # CCXT is critical for any exchange interaction
    ccxt = next((f for f in frameworks if f["name"] == "CCXT"), None)

    if ccxt and not ccxt["installed"]:
        return {
            "name": "Framework Validation",
            "status": "fail",
            "detail": "CCXT not installed — cannot reach exchanges",
        }
    if len(installed) == len(tiers):
        return {
            "name": "Framework Validation",
            "status": "pass",
            "detail": f"{len(installed)}/{len(tiers)} tiers available",
        }
    names = [f["name"] for f in tiers if not f["installed"]]
    return {
        "name": "Framework Validation",
        "status": "warn",
        "detail": f"{len(installed)}/{len(tiers)} tiers — missing: {', '.join(names)}",
    }


def _check_data_freshness() -> CheckResult:
    """Check data pipeline for stale Parquet files."""
    try:
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        from common.data_pipeline.pipeline import validate_all_data

        reports = validate_all_data()
    except Exception as exc:
        return {
            "name": "Data Freshness",
            "status": "warn",
            "detail": f"Could not validate data: {exc}",
        }

    if not reports:
        return {
            "name": "Data Freshness",
            "status": "fail",
            "detail": "No data files found",
        }

    stale = [r for r in reports if r.is_stale]
    ratio = len(stale) / len(reports)

    if ratio == 0:
        return {
            "name": "Data Freshness",
            "status": "pass",
            "detail": f"{len(reports)} files, 0 stale",
        }
    if ratio < 0.5:
        return {
            "name": "Data Freshness",
            "status": "warn",
            "detail": f"{len(stale)}/{len(reports)} files stale",
        }
    return {
        "name": "Data Freshness",
        "status": "fail",
        "detail": f"{len(stale)}/{len(reports)} files stale (>{50}%)",
    }


def _check_database() -> CheckResult:
    """Check SQLite WAL mode and integrity."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        cursor.execute("PRAGMA integrity_check;")
        integrity = cursor.fetchone()[0]

    if integrity != "ok":
        return {
            "name": "Database Health",
            "status": "fail",
            "detail": f"Integrity check: {integrity}",
        }
    return {
        "name": "Database Health",
        "status": "pass",
        "detail": f"WAL={mode}, integrity=ok",
    }


def _check_scheduler() -> CheckResult:
    """Check that the task scheduler is running with key tasks."""
    from core.models import ScheduledTask

    try:
        from core.services.scheduler import get_scheduler

        scheduler = get_scheduler()
        running = scheduler.running
    except Exception:
        running = False

    key_tasks = ["risk_monitoring", "order_sync", "data_refresh_crypto"]
    existing = set(
        ScheduledTask.objects.filter(
            id__in=key_tasks, status=ScheduledTask.ACTIVE,
        ).values_list("id", flat=True)
    )
    missing = [t for t in key_tasks if t not in existing]

    if missing:
        return {
            "name": "Scheduler",
            "status": "fail",
            "detail": f"Missing key tasks: {', '.join(missing)}",
        }
    if not running:
        return {
            "name": "Scheduler",
            "status": "warn",
            "detail": "Scheduler not running (tasks configured but engine stopped)",
        }
    return {
        "name": "Scheduler",
        "status": "pass",
        "detail": f"Running, {len(existing)} key tasks active",
    }


def _check_risk_limits(portfolio_id: int) -> CheckResult:
    """Check risk limits are configured with sane values."""
    from risk.models import RiskLimits

    try:
        limits = RiskLimits.objects.get(portfolio_id=portfolio_id)
    except RiskLimits.DoesNotExist:
        return {
            "name": "Risk Limits",
            "status": "fail",
            "detail": f"No RiskLimits for portfolio {portfolio_id}",
        }

    warnings = []
    if limits.max_portfolio_drawdown > 0.50:
        warnings.append(f"max_drawdown={limits.max_portfolio_drawdown:.0%}")
    if limits.max_daily_loss > 0.20:
        warnings.append(f"max_daily_loss={limits.max_daily_loss:.0%}")
    if limits.max_leverage > 5.0:
        warnings.append(f"max_leverage={limits.max_leverage}")

    if warnings:
        return {
            "name": "Risk Limits",
            "status": "warn",
            "detail": f"Extreme values: {', '.join(warnings)}",
        }
    return {
        "name": "Risk Limits",
        "status": "pass",
        "detail": (
            f"DD={limits.max_portfolio_drawdown:.0%}, "
            f"daily={limits.max_daily_loss:.0%}, "
            f"leverage={limits.max_leverage}x"
        ),
    }


def _check_kill_switch(portfolio_id: int) -> CheckResult:
    """Check that RiskState exists and trading is not halted."""
    from risk.models import RiskState

    try:
        state = RiskState.objects.get(portfolio_id=portfolio_id)
    except RiskState.DoesNotExist:
        return {
            "name": "Kill Switch",
            "status": "fail",
            "detail": f"No RiskState for portfolio {portfolio_id}",
        }

    if state.is_halted:
        return {
            "name": "Kill Switch",
            "status": "warn",
            "detail": f"Trading halted: {state.halt_reason}",
        }
    return {
        "name": "Kill Switch",
        "status": "pass",
        "detail": "Trading active, kill switch ready",
    }


def _check_exchange_config() -> CheckResult:
    """Check exchange configuration — active, sandbox, breakers closed."""
    from market.models import ExchangeConfig
    from market.services.circuit_breaker import get_all_breakers

    configs = ExchangeConfig.objects.filter(is_active=True)
    if not configs.exists():
        return {
            "name": "Exchange Config",
            "status": "warn",
            "detail": "No active exchange configurations",
        }

    sandbox_count = configs.filter(is_sandbox=True).count()
    breakers = get_all_breakers()
    open_breakers = [b for b in breakers if b["state"] == "open"]

    if open_breakers:
        names = [b["exchange_id"] for b in open_breakers]
        return {
            "name": "Exchange Config",
            "status": "fail",
            "detail": f"Circuit breaker OPEN: {', '.join(names)}",
        }

    detail = f"{configs.count()} active, {sandbox_count} sandbox"
    return {
        "name": "Exchange Config",
        "status": "pass",
        "detail": detail,
    }


def _check_notifications() -> CheckResult:
    """Check Telegram notification configuration."""
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")

    if token and chat_id:
        return {
            "name": "Notifications",
            "status": "pass",
            "detail": "Telegram configured",
        }
    return {
        "name": "Notifications",
        "status": "warn",
        "detail": "Telegram not configured — alerts will be log-only",
    }


def _check_disk_space() -> CheckResult:
    """Check available disk space."""
    usage = shutil.disk_usage("/")
    free_gb = usage.free / (1024**3)

    if free_gb < 1:
        return {
            "name": "Disk Space",
            "status": "fail",
            "detail": f"{free_gb:.1f} GB free (<1 GB)",
        }
    if free_gb < 5:
        return {
            "name": "Disk Space",
            "status": "warn",
            "detail": f"{free_gb:.1f} GB free (1-5 GB)",
        }
    return {
        "name": "Disk Space",
        "status": "pass",
        "detail": f"{free_gb:.1f} GB free",
    }


def _check_portfolio(portfolio_id: int) -> CheckResult:
    """Check that the target portfolio exists."""
    from portfolio.models import Portfolio

    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)
    except Portfolio.DoesNotExist:
        return {
            "name": "Portfolio",
            "status": "fail",
            "detail": f"Portfolio {portfolio_id} not found",
        }

    return {
        "name": "Portfolio",
        "status": "pass",
        "detail": f"'{portfolio.name}' (id={portfolio.id})",
    }


class Command(BaseCommand):
    help = "Run pre-flight checklist for the live trading pilot"

    def add_arguments(self, parser):
        parser.add_argument(
            "--json", action="store_true", help="Output results as JSON",
        )
        parser.add_argument(
            "--portfolio-id", type=int, default=1, help="Portfolio ID to check (default: 1)",
        )

    def handle(self, *args, **options):
        portfolio_id: int = options["portfolio_id"]
        as_json: bool = options["json"]

        checks: list[CheckResult] = [
            _check_frameworks(),
            _check_data_freshness(),
            _check_database(),
            _check_scheduler(),
            _check_risk_limits(portfolio_id),
            _check_kill_switch(portfolio_id),
            _check_exchange_config(),
            _check_notifications(),
            _check_disk_space(),
            _check_portfolio(portfolio_id),
        ]

        fails = [c for c in checks if c["status"] == "fail"]
        warns = [c for c in checks if c["status"] == "warn"]
        go = len(fails) == 0

        if as_json:
            self.stdout.write(json.dumps({
                "checks": checks,
                "summary": {
                    "total": len(checks),
                    "pass": len(checks) - len(fails) - len(warns),
                    "warn": len(warns),
                    "fail": len(fails),
                    "go": go,
                },
            }, indent=2))
        else:
            self.stdout.write("\n  Pre-Flight Checklist\n")
            for check in checks:
                status = check["status"].upper()
                if status == "PASS":
                    tag = self.style.SUCCESS(f"[{status}]")
                elif status == "WARN":
                    tag = self.style.WARNING(f"[{status}]")
                else:
                    tag = self.style.ERROR(f"[{status}]")
                self.stdout.write(f"  {tag} {check['name']}: {check['detail']}")

            self.stdout.write("")
            p = len(checks) - len(fails) - len(warns)
            summary = f"  {p} pass, {len(warns)} warn, {len(fails)} fail"
            if go:
                self.stdout.write(self.style.SUCCESS(f"  GO — {summary}"))
            else:
                self.stdout.write(self.style.ERROR(f"  NO-GO — {summary}"))

        if not go:
            sys.exit(1)
