"""PDF Report Data Collector — aggregates data from existing services.

Calls existing services and queries existing models to collect all data
needed for the daily PDF intelligence report. Does NOT duplicate any
business logic.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class PDFReportDataCollector:
    """Aggregates data from existing services for the daily PDF report."""

    @staticmethod
    def collect(portfolio_id: int = 1, lookback_days: int = 30) -> dict[str, Any]:
        """Collect all data sections for the PDF report.

        Each section is collected in its own try/except so that a failure
        in one section does not prevent the rest of the report from being
        generated.

        Args:
            portfolio_id: The portfolio to collect data for.
            lookback_days: How many days of history to include.

        Returns:
            Dict with all report sections.
        """
        data: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "portfolio_id": portfolio_id,
            "lookback_days": lookback_days,
        }

        data["portfolio"] = PDFReportDataCollector._collect_portfolio(portfolio_id)
        data["trading"] = PDFReportDataCollector._collect_trading(portfolio_id)
        data["strategy_breakdown"] = PDFReportDataCollector._collect_strategy_breakdown()
        data["risk"] = PDFReportDataCollector._collect_risk(portfolio_id)
        data["equity_history"] = PDFReportDataCollector._collect_equity_history(
            portfolio_id, lookback_days,
        )
        data["daily_pnl_history"] = PDFReportDataCollector._compute_daily_pnl(
            data["equity_history"],
        )
        data["weekly_pnl_history"] = PDFReportDataCollector._compute_weekly_pnl(
            data["daily_pnl_history"],
        )
        data["regime"] = PDFReportDataCollector._collect_regime()
        data["opportunities"] = PDFReportDataCollector._collect_opportunities()
        data["ml"] = PDFReportDataCollector._collect_ml()
        data["attribution"] = PDFReportDataCollector._collect_attribution(lookback_days)
        data["weights"] = PDFReportDataCollector._collect_weights(lookback_days)
        data["orchestrator"] = PDFReportDataCollector._collect_orchestrator()
        data["system"] = PDFReportDataCollector._collect_system()

        return data

    # ── Section collectors ────────────────────────────────────────

    @staticmethod
    def _collect_portfolio(portfolio_id: int) -> dict[str, Any]:
        """Portfolio equity, cost, and P&L from DashboardService."""
        try:
            from core.services.dashboard import DashboardService

            return DashboardService._get_portfolio_kpis()
        except Exception as e:
            logger.warning("PDF data: portfolio collection failed: %s", e)
            return {
                "count": 0,
                "total_value": 0.0,
                "total_cost": 0.0,
                "unrealized_pnl": 0.0,
                "pnl_pct": 0.0,
            }

    @staticmethod
    def _collect_trading(portfolio_id: int) -> dict[str, Any]:
        """Win rate, P&L, profit factor from TradingPerformanceService."""
        try:
            from trading.services.performance import TradingPerformanceService

            return TradingPerformanceService.get_summary(portfolio_id)
        except Exception as e:
            logger.warning("PDF data: trading collection failed: %s", e)
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "profit_factor": None,
            }

    @staticmethod
    def _collect_strategy_breakdown() -> list[dict[str, Any]]:
        """Per-strategy P&L from Freqtrade API instances + forex paper trading."""
        results: list[dict[str, Any]] = []

        # Freqtrade instances
        ft_instances = getattr(settings, "FREQTRADE_INSTANCES", [])
        ft_user = getattr(settings, "FREQTRADE_USERNAME", "freqtrader")
        ft_pass = getattr(settings, "FREQTRADE_PASSWORD", "freqtrader")

        for instance in ft_instances:
            name = instance.get("name", "unknown")
            if not instance.get("enabled", True):
                results.append({
                    "name": name,
                    "source": "freqtrade",
                    "running": False,
                    "pnl": 0.0,
                    "trade_count": 0,
                    "open_trades": 0,
                })
                continue

            url = instance.get("url", "")
            if not url:
                continue

            try:
                profit_resp = requests.get(
                    f"{url}/api/v1/profit",
                    auth=(ft_user, ft_pass),
                    timeout=5,
                )
                profit_resp.raise_for_status()
                profit = profit_resp.json()

                trade_count = profit.get("trade_count", 0) or 0
                closed_count = profit.get("closed_trade_count", 0) or 0

                results.append({
                    "name": name,
                    "source": "freqtrade",
                    "running": True,
                    "pnl": round(profit.get("profit_all_coin", 0) or 0, 2),
                    "pnl_pct": round(profit.get("profit_all_percent", 0) or 0, 2),
                    "trade_count": trade_count,
                    "closed_trades": closed_count,
                    "open_trades": max(trade_count - closed_count, 0),
                    "winning_trades": profit.get("winning_trades", 0) or 0,
                    "losing_trades": profit.get("losing_trades", 0) or 0,
                })
            except Exception as e:
                logger.debug("PDF data: Freqtrade %s unavailable: %s", name, e)
                results.append({
                    "name": name,
                    "source": "freqtrade",
                    "running": False,
                    "pnl": 0.0,
                    "trade_count": 0,
                    "open_trades": 0,
                })

        # Forex paper trading
        try:
            from trading.services.forex_paper_trading import ForexPaperTradingService

            forex_svc = ForexPaperTradingService()
            forex_profit = forex_svc.get_profit()
            forex_status = forex_svc.get_status()

            trade_count = forex_profit.get("trade_count", 0) or 0
            closed_count = forex_profit.get("closed_trade_count", 0) or 0

            results.append({
                "name": "ForexSignals",
                "source": "forex_paper",
                "running": forex_status.get("running", False),
                "pnl": round(forex_profit.get("profit_all_coin", 0) or 0, 2),
                "pnl_pct": round(forex_profit.get("profit_all_percent", 0) or 0, 2),
                "trade_count": trade_count,
                "closed_trades": closed_count,
                "open_trades": max(trade_count - closed_count, 0),
                "winning_trades": forex_profit.get("winning_trades", 0) or 0,
                "losing_trades": forex_profit.get("losing_trades", 0) or 0,
            })
        except Exception as e:
            logger.debug("PDF data: forex paper trading unavailable: %s", e)

        return results

    @staticmethod
    def _collect_risk(portfolio_id: int) -> dict[str, Any]:
        """Equity, drawdown, daily P&L, halted status from RiskManagementService."""
        try:
            from risk.services.risk import RiskManagementService

            return RiskManagementService.get_status(portfolio_id)
        except Exception as e:
            logger.warning("PDF data: risk collection failed: %s", e)
            return {
                "equity": 0.0,
                "peak_equity": 0.0,
                "drawdown": 0.0,
                "daily_pnl": 0.0,
                "total_pnl": 0.0,
                "open_positions": 0,
                "is_halted": False,
                "halt_reason": "",
            }

    @staticmethod
    def _collect_equity_history(
        portfolio_id: int,
        lookback_days: int,
    ) -> list[dict[str, Any]]:
        """Equity snapshots from RiskMetricHistory, resampled to hourly."""
        try:
            from risk.models import RiskMetricHistory

            cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
            records = RiskMetricHistory.objects.filter(
                portfolio_id=portfolio_id,
                recorded_at__gte=cutoff,
            ).order_by("recorded_at")

            # Resample to hourly by keeping the last record per hour
            hourly: dict[str, dict[str, Any]] = {}
            for record in records:
                hour_key = record.recorded_at.strftime("%Y-%m-%d %H:00")
                hourly[hour_key] = {
                    "timestamp": record.recorded_at.isoformat(),
                    "hour": hour_key,
                    "equity": record.equity,
                    "drawdown": record.drawdown,
                    "var_95": record.var_95,
                    "open_positions": record.open_positions_count,
                }

            return list(hourly.values())
        except Exception as e:
            logger.warning("PDF data: equity history collection failed: %s", e)
            return []

    @staticmethod
    def _compute_daily_pnl(
        equity_history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Compute daily P&L from hourly equity snapshots.

        Groups equity snapshots by date. For each date, computes the
        opening equity (first snapshot), closing equity (last snapshot),
        and the daily P&L as the difference.
        """
        if not equity_history:
            return []

        try:
            by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for entry in equity_history:
                date_key = entry["timestamp"][:10]  # YYYY-MM-DD
                by_date[date_key].append(entry)

            daily: list[dict[str, Any]] = []
            for date_str in sorted(by_date.keys()):
                entries = by_date[date_str]
                open_equity = entries[0]["equity"]
                close_equity = entries[-1]["equity"]
                pnl = close_equity - open_equity
                pnl_pct = (pnl / open_equity * 100) if open_equity > 0 else 0.0

                daily.append({
                    "date": date_str,
                    "open_equity": round(open_equity, 2),
                    "close_equity": round(close_equity, 2),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "snapshots": len(entries),
                })

            return daily
        except Exception as e:
            logger.warning("PDF data: daily P&L computation failed: %s", e)
            return []

    @staticmethod
    def _compute_weekly_pnl(
        daily_pnl_history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Aggregate daily P&L into weekly buckets (Monday-Sunday)."""
        if not daily_pnl_history:
            return []

        try:
            by_week: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for entry in daily_pnl_history:
                date = datetime.strptime(entry["date"], "%Y-%m-%d")
                # ISO week: Monday is the start of the week
                week_start = date - timedelta(days=date.weekday())
                week_key = week_start.strftime("%Y-%m-%d")
                by_week[week_key].append(entry)

            weekly: list[dict[str, Any]] = []
            for week_start_str in sorted(by_week.keys()):
                days = by_week[week_start_str]
                total_pnl = sum(d["pnl"] for d in days)
                open_equity = days[0]["open_equity"]
                close_equity = days[-1]["close_equity"]
                pnl_pct = (total_pnl / open_equity * 100) if open_equity > 0 else 0.0

                weekly.append({
                    "week_start": week_start_str,
                    "days": len(days),
                    "open_equity": round(open_equity, 2),
                    "close_equity": round(close_equity, 2),
                    "pnl": round(total_pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                })

            return weekly
        except Exception as e:
            logger.warning("PDF data: weekly P&L computation failed: %s", e)
            return []

    @staticmethod
    def _collect_regime() -> dict[str, Any]:
        """Current regime and regime distribution from RegimeService."""
        try:
            from market.services.regime import RegimeService

            service = RegimeService()
            regimes = service.get_all_current_regimes()

            if not regimes:
                return {"status": "no_data", "regimes": [], "distribution": {}}

            distribution: dict[str, int] = {}
            for r in regimes:
                regime = r.get("regime", "unknown")
                distribution[regime] = distribution.get(regime, 0) + 1

            avg_confidence = sum(r.get("confidence", 0) for r in regimes) / len(regimes)
            dominant = max(distribution, key=distribution.get) if distribution else "unknown"

            return {
                "status": "ok",
                "symbols_analyzed": len(regimes),
                "distribution": distribution,
                "avg_confidence": round(avg_confidence, 2),
                "dominant_regime": dominant,
                "regimes": regimes,
            }
        except Exception as e:
            logger.warning("PDF data: regime collection failed: %s", e)
            return {"status": "error", "error": str(e), "regimes": [], "distribution": {}}

    @staticmethod
    def _collect_opportunities() -> list[dict[str, Any]]:
        """Top 5 active market opportunities by score."""
        try:
            from django.utils import timezone as tz

            from market.models import MarketOpportunity

            now = tz.now()
            opps = MarketOpportunity.objects.filter(
                expires_at__gt=now,
            ).order_by("-score")[:5]

            return [
                {
                    "symbol": o.symbol,
                    "type": o.opportunity_type,
                    "asset_class": o.asset_class,
                    "score": o.score,
                    "details": o.details,
                    "detected_at": o.detected_at.isoformat(),
                }
                for o in opps
            ]
        except Exception as e:
            logger.warning("PDF data: opportunities collection failed: %s", e)
            return []

    @staticmethod
    def _collect_ml() -> dict[str, Any]:
        """ML accuracy, prediction count, model count from DashboardService."""
        try:
            from core.services.dashboard import DashboardService

            return DashboardService._get_learning_status()
        except Exception as e:
            logger.warning("PDF data: ML collection failed: %s", e)
            return {
                "ml_accuracy": None,
                "ml_predictions_total": 0,
                "ml_models_count": 0,
                "ml_last_trained": None,
                "signal_attributions": 0,
                "orchestrator_states": [],
            }

    @staticmethod
    def _collect_attribution(lookback_days: int) -> dict[str, Any]:
        """Signal source accuracy from SignalFeedbackService."""
        try:
            from analysis.services.signal_feedback import SignalFeedbackService

            return SignalFeedbackService.get_source_accuracy(window_days=lookback_days)
        except Exception as e:
            logger.warning("PDF data: attribution collection failed: %s", e)
            return {
                "total_trades": 0,
                "wins": 0,
                "overall_win_rate": 0.0,
                "window_days": lookback_days,
                "sources": {},
            }

    @staticmethod
    def _collect_weights(lookback_days: int) -> dict[str, Any]:
        """Weight recommendations from SignalFeedbackService."""
        try:
            from analysis.services.signal_feedback import SignalFeedbackService

            return SignalFeedbackService.get_weight_recommendations(
                window_days=lookback_days,
            )
        except Exception as e:
            logger.warning("PDF data: weights collection failed: %s", e)
            return {"error": str(e)}

    @staticmethod
    def _collect_orchestrator() -> list[dict[str, Any]]:
        """Strategy states from StrategyOrchestrator."""
        try:
            from trading.services.strategy_orchestrator import StrategyOrchestrator

            orchestrator = StrategyOrchestrator.get_instance()
            states = orchestrator.get_all_states()

            return [
                {
                    "strategy": s.strategy,
                    "asset_class": s.asset_class,
                    "regime": s.regime,
                    "alignment": s.alignment,
                    "action": s.action,
                    "updated_at": s.updated_at.isoformat(),
                }
                for s in states
            ]
        except Exception as e:
            logger.warning("PDF data: orchestrator collection failed: %s", e)
            return []

    @staticmethod
    def _collect_system() -> dict[str, Any]:
        """Scheduler health, job counts from DashboardService."""
        try:
            from core.services.dashboard import DashboardService

            return DashboardService._get_system_health()
        except Exception as e:
            logger.warning("PDF data: system health collection failed: %s", e)
            return {
                "scheduler_running": False,
                "last_data_refresh": None,
                "freqtrade_instances": [],
                "active_tasks": 0,
                "total_jobs_completed": 0,
                "total_jobs_failed": 0,
            }
