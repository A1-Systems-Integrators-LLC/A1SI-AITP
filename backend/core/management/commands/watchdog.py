"""System watchdog — check platform health and optionally auto-fix issues.

Runs health checks on all subsystems and can auto-remediate common problems
like corrupted risk state, stale daily P&L, and halted trading caused by
data sync errors.

Usage:
    manage.py watchdog                      # Report health
    manage.py watchdog --json               # JSON output
    manage.py watchdog --fix                # Auto-fix detected issues
    manage.py watchdog --reset-daily        # Reset daily P&L counters
    manage.py watchdog --fix-equity VALUE   # Set equity to specific value
    manage.py watchdog --resume             # Resume halted trading
"""

import json
import sys
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

CheckResult = dict[str, Any]


def _check_database() -> CheckResult:
    """Verify SQLite connectivity and journal mode."""
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0]
    except Exception as e:
        return {"name": "Database", "status": "fail", "detail": str(e)}

    if mode == "wal":
        return {"name": "Database", "status": "fail", "detail": "CRITICAL: WAL mode detected"}
    return {"name": "Database", "status": "pass", "detail": f"journal={mode}"}


def _check_scheduler() -> CheckResult:
    """Check that APScheduler is running (via health endpoint or direct check)."""
    # First try the health endpoint (checks the actual Daphne process)
    try:
        resp = requests.get(
            "http://localhost:8000/api/health/?detailed=true", timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            sched = data.get("checks", {}).get("scheduler", {})
            if sched.get("running"):
                return {
                    "name": "Scheduler", "status": "pass",
                    "detail": "Running (via health endpoint)",
                }
            return {
                "name": "Scheduler", "status": "fail",
                "detail": "Not running (health endpoint reports down)",
            }
    except Exception:
        pass

    # Fallback: direct check (only works in same process)
    try:
        from core.services.scheduler import get_scheduler

        scheduler = get_scheduler()
        if scheduler.running:
            return {
                "name": "Scheduler", "status": "pass",
                "detail": "Running (direct check)",
            }
        return {
            "name": "Scheduler", "status": "warn",
            "detail": "Not running in this process (check Daphne)",
        }
    except Exception as e:
        return {"name": "Scheduler", "status": "fail", "detail": str(e)}


def _check_risk_state(portfolio_id: int) -> CheckResult:
    """Check risk state for corruption or halts."""
    from risk.models import RiskState

    try:
        state = RiskState.objects.get(portfolio_id=portfolio_id)
    except RiskState.DoesNotExist:
        return {"name": "Risk State", "status": "fail", "detail": "No RiskState found"}

    issues = []

    if state.is_halted:
        issues.append(f"HALTED: {state.halt_reason}")

    # Detect equity corruption: equity dropped to near-zero or negative
    if state.total_equity <= 0:
        issues.append(f"Equity is {state.total_equity} (zero or negative)")

    # Detect suspicious drawdown: >50% drawdown with near-zero daily_pnl
    if state.peak_equity > 0:
        drawdown = 1.0 - (state.total_equity / state.peak_equity)
        if drawdown > 0.30 and abs(state.daily_pnl) < 1.0:
            issues.append(
                f"Suspicious: {drawdown:.0%} drawdown but daily_pnl=${state.daily_pnl:.2f} "
                f"(likely sync corruption, not real losses)"
            )

    if issues:
        return {
            "name": "Risk State",
            "status": "fail",
            "detail": "; ".join(issues),
            "data": {
                "equity": float(state.total_equity),
                "peak": float(state.peak_equity),
                "daily_pnl": float(state.daily_pnl),
                "daily_start": float(state.daily_start_equity),
                "halted": state.is_halted,
                "halt_reason": state.halt_reason,
            },
        }

    return {
        "name": "Risk State",
        "status": "pass",
        "detail": f"equity=${state.total_equity:.2f}, halted={state.is_halted}",
    }


def _check_freqtrade() -> CheckResult:
    """Ping all configured Freqtrade instances."""
    ft_user = getattr(settings, "FREQTRADE_USERNAME", "")
    ft_pass = getattr(settings, "FREQTRADE_PASSWORD", "")

    urls = {
        "CIV1": getattr(settings, "FREQTRADE_API_URL", "") or "http://127.0.0.1:4080",
        "BMR": getattr(settings, "FREQTRADE_BMR_API_URL", "") or "http://127.0.0.1:4083",
        "VB": getattr(settings, "FREQTRADE_VB_API_URL", "") or "http://127.0.0.1:4084",
    }

    alive = []
    dead = []
    for name, url in urls.items():
        if not url:
            dead.append(name)
            continue
        try:
            resp = requests.get(f"{url}/api/v1/ping", auth=(ft_user, ft_pass), timeout=5)
            if resp.status_code == 200:
                alive.append(name)
            else:
                dead.append(name)
        except Exception:
            dead.append(name)

    if not dead:
        return {
            "name": "Freqtrade", "status": "pass",
            "detail": f"All {len(alive)} instances running",
        }
    if alive:
        return {
            "name": "Freqtrade",
            "status": "warn",
            "detail": f"{len(alive)}/{len(urls)} running, down: {', '.join(dead)}",
        }
    return {
        "name": "Freqtrade",
        "status": "fail",
        "detail": f"All {len(urls)} instances down",
        "dead": dead,
    }


def _check_rejected_orders(portfolio_id: int) -> CheckResult:
    """Check for excessive recent order rejections."""
    from datetime import datetime, timedelta, timezone

    from trading.models import Order

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_rejected = Order.objects.filter(
        status="rejected", created_at__gte=cutoff,
    ).count()

    if recent_rejected > 50:
        return {
            "name": "Order Rejections",
            "status": "fail",
            "detail": f"{recent_rejected} rejected in last hour (risk gate likely broken)",
        }
    if recent_rejected > 10:
        return {
            "name": "Order Rejections",
            "status": "warn",
            "detail": f"{recent_rejected} rejected in last hour",
        }
    return {
        "name": "Order Rejections",
        "status": "pass",
        "detail": f"{recent_rejected} rejected in last hour",
    }


def _check_stale_jobs() -> CheckResult:
    """Check for stuck or stale background jobs."""
    from datetime import datetime, timedelta, timezone

    from analysis.models import BackgroundJob

    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    stuck = BackgroundJob.objects.filter(
        status="running", started_at__lt=cutoff,
    ).count()

    if stuck > 0:
        return {"name": "Background Jobs", "status": "warn", "detail": f"{stuck} stuck jobs (>2h)"}
    return {"name": "Background Jobs", "status": "pass", "detail": "No stuck jobs"}


class Command(BaseCommand):
    help = "System watchdog: check platform health and optionally auto-fix issues"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--fix", action="store_true", help="Auto-fix detected issues")
        parser.add_argument("--reset-daily", action="store_true", help="Reset daily P&L counters")
        parser.add_argument("--resume", action="store_true", help="Resume halted trading")
        parser.add_argument(
            "--fix-equity", type=float, default=None,
            help="Set equity to specific value (e.g. 500.0)",
        )
        parser.add_argument(
            "--portfolio-id", type=int, default=1, help="Portfolio ID (default: 1)",
        )

    def handle(self, *args, **options):
        portfolio_id: int = options["portfolio_id"]
        as_json: bool = options["json"]

        # Run all checks
        checks: list[CheckResult] = [
            _check_database(),
            _check_scheduler(),
            _check_risk_state(portfolio_id),
            _check_freqtrade(),
            _check_rejected_orders(portfolio_id),
            _check_stale_jobs(),
        ]

        fixes: list[dict] = []

        # ── Apply fixes ──
        if options["reset_daily"]:
            fixes.append(self._do_reset_daily(portfolio_id))

        if options["fix_equity"] is not None:
            fixes.append(self._do_fix_equity(portfolio_id, options["fix_equity"]))

        if options["resume"]:
            fixes.append(self._do_resume(portfolio_id))

        if options["fix"]:
            fixes.extend(self._auto_fix(checks, portfolio_id))

        # ── Output ──
        fails = [c for c in checks if c["status"] == "fail"]
        warns = [c for c in checks if c["status"] == "warn"]
        healthy = len(fails) == 0

        if as_json:
            self.stdout.write(json.dumps({
                "checks": checks,
                "fixes": fixes,
                "summary": {
                    "total": len(checks),
                    "pass": len(checks) - len(fails) - len(warns),
                    "warn": len(warns),
                    "fail": len(fails),
                    "healthy": healthy,
                },
            }, indent=2))
        else:
            self.stdout.write("\n  System Watchdog\n")
            for check in checks:
                status = check["status"].upper()
                if status == "PASS":
                    tag = self.style.SUCCESS(f"[{status}]")
                elif status == "WARN":
                    tag = self.style.WARNING(f"[{status}]")
                else:
                    tag = self.style.ERROR(f"[{status}]")
                self.stdout.write(f"  {tag} {check['name']}: {check['detail']}")

            if fixes:
                self.stdout.write("\n  Fixes Applied:")
                for fix in fixes:
                    status = "OK" if fix.get("success") else "FAILED"
                    if fix.get("success"):
                        tag = self.style.SUCCESS(f"[{status}]")
                    else:
                        tag = self.style.ERROR(f"[{status}]")
                    self.stdout.write(f"  {tag} {fix['action']}: {fix.get('detail', '')}")

            self.stdout.write("")
            p = len(checks) - len(fails) - len(warns)
            summary = f"  {p} pass, {len(warns)} warn, {len(fails)} fail"
            if healthy:
                self.stdout.write(self.style.SUCCESS(f"  HEALTHY — {summary}"))
            else:
                self.stdout.write(self.style.ERROR(f"  UNHEALTHY — {summary}"))

        if not healthy and not options["fix"]:
            sys.exit(1)

    def _do_reset_daily(self, portfolio_id: int) -> dict:
        """Reset daily P&L counters."""
        try:
            from risk.services.risk import RiskManagementService

            result = RiskManagementService.reset_daily(portfolio_id)
            return {
                "action": "Reset daily P&L",
                "success": True,
                "detail": f"equity=${result['equity']:.2f}, daily_pnl=${result['daily_pnl']:.2f}",
            }
        except Exception as e:
            return {"action": "Reset daily P&L", "success": False, "detail": str(e)}

    def _do_fix_equity(self, portfolio_id: int, equity: float) -> dict:
        """Set equity to a specific value and reset peak/daily."""
        try:
            from risk.models import RiskState

            state, _ = RiskState.objects.get_or_create(portfolio_id=portfolio_id)
            old_equity = state.total_equity
            state.total_equity = equity
            state.peak_equity = equity  # Reset peak to match corrected equity
            state.daily_start_equity = equity
            state.daily_pnl = 0.0
            state.total_pnl = 0.0
            state.is_halted = False
            state.halt_reason = ""
            state.save()
            return {
                "action": "Fix equity",
                "success": True,
                "detail": f"${old_equity:.2f} -> ${equity:.2f}, halted=False, daily reset",
            }
        except Exception as e:
            return {"action": "Fix equity", "success": False, "detail": str(e)}

    def _do_resume(self, portfolio_id: int) -> dict:
        """Resume halted trading."""
        try:
            from risk.services.risk import RiskManagementService

            result = RiskManagementService.resume_trading(portfolio_id)
            msg = result.get("message", "")
            return {"action": "Resume trading", "success": True, "detail": msg}
        except Exception as e:
            return {"action": "Resume trading", "success": False, "detail": str(e)}

    def _auto_fix(self, checks: list[CheckResult], portfolio_id: int) -> list[dict]:
        """Automatically fix issues detected by checks."""
        fixes = []

        risk_check = next((c for c in checks if c["name"] == "Risk State"), None)
        if risk_check and risk_check["status"] == "fail":
            data = risk_check.get("data", {})

            # Auto-resume if halted due to sync corruption (drawdown with near-zero daily_pnl)
            if data.get("halted"):
                halt_reason = data.get("halt_reason", "")
                # Check if this looks like sync corruption vs real losses
                if "drawdown" in halt_reason.lower() or "Max drawdown" in halt_reason:
                    daily_pnl = data.get("daily_pnl", 0)
                    peak = data.get("peak", 0)
                    # If daily P&L is tiny but drawdown is huge, it's corruption
                    if peak > 0 and abs(daily_pnl) < peak * 0.02:
                        # Reset equity to a sane value based on configured wallets
                        from django.conf import settings as s
                        ft_instances = getattr(s, "FREQTRADE_INSTANCES", [])
                        wallet_total = sum(i.get("dry_run_wallet", 0) for i in ft_instances[:3])
                        if wallet_total <= 0:
                            wallet_total = 500.0
                        fixes.append(self._do_fix_equity(portfolio_id, wallet_total))
                        fixes.append(self._do_reset_daily(portfolio_id))
                    else:
                        # Real losses — just resume, don't change equity
                        fixes.append(self._do_resume(portfolio_id))
                        fixes.append(self._do_reset_daily(portfolio_id))

            # Auto-fix zero/negative equity
            elif data.get("equity", 0) <= 0:
                from django.conf import settings as s
                ft_instances = getattr(s, "FREQTRADE_INSTANCES", [])
                wallet_total = sum(i.get("dry_run_wallet", 0) for i in ft_instances[:3])
                if wallet_total <= 0:
                    wallet_total = 500.0
                fixes.append(self._do_fix_equity(portfolio_id, wallet_total))

        return fixes
