"""PDF Report Data Collector — aggregates data from existing services.

Calls existing services and queries existing models to collect all data
needed for the daily PDF intelligence report. Does NOT duplicate any
business logic.

Enhanced version: collects team assessments, decision logs, news intelligence,
and improvement recommendations for a comprehensive daily briefing.
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
        """
        data: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "portfolio_id": portfolio_id,
            "lookback_days": lookback_days,
        }

        # ── Core metrics (existing) ──────────────────────────────
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

        # ── NEW: Enhanced sections ───────────────────────────────
        data["news_intelligence"] = PDFReportDataCollector._collect_news_intelligence()
        data["sentiment_history"] = PDFReportDataCollector._collect_sentiment_history()
        data["decisions"] = PDFReportDataCollector._collect_decisions()
        data["team_assessments"] = PDFReportDataCollector._generate_team_assessments(data)
        data["recommendations"] = PDFReportDataCollector._generate_recommendations(data)
        data["lessons_learned"] = PDFReportDataCollector._generate_lessons_learned(data)

        return data

    # ── Existing Section Collectors ────────────────────────────────

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

        ft_instances = getattr(settings, "FREQTRADE_INSTANCES", [])
        ft_user = getattr(settings, "FREQTRADE_USERNAME", "")
        ft_pass = getattr(settings, "FREQTRADE_PASSWORD", "")

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
        """Compute daily P&L from hourly equity snapshots."""
        if not equity_history:
            return []

        try:
            by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for entry in equity_history:
                date_key = entry["timestamp"][:10]
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

    # ══════════════════════════════════════════════════════════════════
    # NEW: Enhanced Data Sections
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _collect_news_intelligence() -> dict[str, Any]:
        """Collect news articles and sentiment summary for the past 24h."""
        result: dict[str, Any] = {
            "articles": [],
            "sentiment_summary": {},
            "sentiment_signal": {},
            "top_themes": [],
        }

        try:
            from market.services.news import NewsService

            svc = NewsService()

            # Recent articles
            articles = svc.get_articles(limit=15)
            result["articles"] = articles[:15]

            # Sentiment summaries per asset class
            for ac in ["crypto", "equity", "forex"]:
                try:
                    summary = svc.get_sentiment_summary(asset_class=ac, hours=24)
                    signal = svc.get_sentiment_signal(asset_class=ac, hours=24)
                    result["sentiment_summary"][ac] = summary
                    result["sentiment_signal"][ac] = signal
                except Exception:
                    pass

            # Extract top themes from article titles
            result["top_themes"] = _extract_themes(articles)

        except Exception as e:
            logger.warning("PDF data: news intelligence collection failed: %s", e)

        return result

    @staticmethod
    def _collect_sentiment_history() -> list[dict[str, Any]]:
        """Collect daily sentiment scores for the past 7 days for charting."""
        history: list[dict[str, Any]] = []
        try:
            from market.models import NewsArticle

            now = datetime.now(timezone.utc)
            for days_ago in range(6, -1, -1):
                date = now - timedelta(days=days_ago)
                date_str = date.strftime("%Y-%m-%d")
                start = date.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1)

                articles = NewsArticle.objects.filter(
                    published_at__gte=start,
                    published_at__lt=end,
                )
                count = articles.count()
                if count == 0:
                    history.append({
                        "date": date_str,
                        "signal": 0,
                        "conviction": 0,
                        "label": "neutral",
                        "article_count": 0,
                    })
                    continue

                scores = [a.sentiment_score for a in articles if a.sentiment_score is not None]
                avg_score = sum(scores) / len(scores) if scores else 0
                conviction = min(1.0, count / 20)  # Normalize against threshold
                if avg_score > 0.15:
                    label = "bullish"
                elif avg_score < -0.15:
                    label = "bearish"
                else:
                    label = "neutral"

                history.append({
                    "date": date_str,
                    "signal": round(avg_score, 3),
                    "conviction": round(conviction, 2),
                    "label": label,
                    "article_count": count,
                })
        except Exception as e:
            logger.warning("PDF data: sentiment history collection failed: %s", e)

        return history

    @staticmethod
    def _collect_decisions() -> list[dict[str, Any]]:
        """Collect key decisions made in the last 24h from AlertLog and audit trail.

        Decisions include: orchestrator state changes, risk halts/resumes,
        signal weight adjustments, kill switch activations, and auto-actions.
        """
        decisions: list[dict[str, Any]] = []

        try:
            from risk.models import AlertLog

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

            # Key decision-related events from AlertLog
            decision_events = [
                "orchestrator_transition",
                "risk_halt",
                "risk_resume",
                "kill_switch_activated",
                "kill_switch_deactivated",
                "risk_warning",
                "strategy_paused",
                "strategy_resumed",
                "auto_halt",
                "drawdown_warning",
                "daily_loss_warning",
            ]

            alerts = AlertLog.objects.filter(
                created_at__gte=cutoff,
                event_type__in=decision_events,
            ).order_by("-created_at")[:20]

            for alert in alerts:
                decisions.append({
                    "timestamp": alert.created_at.isoformat(),
                    "event": alert.event_type,
                    "severity": alert.severity,
                    "message": alert.message,
                    "category": _categorize_decision(alert.event_type),
                })
        except Exception as e:
            logger.warning("PDF data: decision collection from AlertLog failed: %s", e)

        # Also check for risk limit changes
        try:
            from risk.models import RiskLimitChange

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            changes = RiskLimitChange.objects.filter(
                changed_at__gte=cutoff,
            ).order_by("-changed_at")[:10]

            for change in changes:
                decisions.append({
                    "timestamp": change.changed_at.isoformat(),
                    "event": "risk_limit_change",
                    "severity": "info",
                    "message": (
                        f"Risk limit '{change.field}' changed "
                        f"from {change.old_value} to {change.new_value}"
                        + (f" — Reason: {change.reason}" if change.reason else "")
                    ),
                    "category": "Risk Management",
                })
        except Exception as e:
            logger.debug("PDF data: risk limit changes collection failed: %s", e)

        # Sort all decisions by timestamp descending
        decisions.sort(key=lambda d: d.get("timestamp", ""), reverse=True)
        return decisions

    @staticmethod
    def _generate_team_assessments(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Generate specialist assessments based on collected data.

        Each specialist analyzes their domain and produces:
        - health_score (0-100)
        - status (good/warning/critical)
        - findings (list of observations)
        - concerns (list of issues)
        """
        assessments: dict[str, dict[str, Any]] = {}

        # ── Quant Developer Assessment ──
        assessments["quant"] = _assess_quant(data)

        # ── Strategy Engineer Assessment ──
        assessments["strategy"] = _assess_strategy(data)

        # ── Risk Manager Assessment ──
        assessments["risk"] = _assess_risk(data)

        # ── Data Engineer Assessment ──
        assessments["data"] = _assess_data(data)

        # ── ML Engineer Assessment ──
        assessments["ml"] = _assess_ml(data)

        # ── Market Analyst Assessment ──
        assessments["market"] = _assess_market(data)

        return assessments

    @staticmethod
    def _generate_recommendations(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate actionable improvement recommendations from all data sources."""
        recs: list[dict[str, Any]] = []

        # ── From signal weight analysis ──
        weights = data.get("weights", {})
        adjustments = weights.get("adjustments", {})
        reasoning = weights.get("reasoning", [])
        for reason in reasoning:
            recs.append({
                "source": "Signal Analysis",
                "priority": "high",
                "recommendation": reason,
                "category": "Signal Weights",
            })

        for source, adj in adjustments.items():
            adj_val = float(adj) if adj else 0
            if abs(adj_val) > 0.02:
                direction = "Increase" if adj_val > 0 else "Decrease"
                recs.append({
                    "source": "Signal Analysis",
                    "priority": "medium",
                    "recommendation": f"{direction} {source} weight by {abs(adj_val):.3f} "
                                      f"based on recent attribution accuracy.",
                    "category": "Signal Weights",
                })

        # ── From ML performance ──
        ml = data.get("ml", {})
        ml_accuracy = ml.get("ml_accuracy") or 0
        if ml_accuracy > 0 and ml_accuracy < 52:
            recs.append({
                "source": "ML Engineer",
                "priority": "high",
                "recommendation": (
                    f"ML accuracy at {ml_accuracy:.1f}% is below random. "
                    "Consider retraining with updated features "
                    "or disabling ML signal."
                ),
                "category": "Machine Learning",
            })
        elif ml_accuracy >= 52 and ml_accuracy < 55:
            recs.append({
                "source": "ML Engineer",
                "priority": "medium",
                "recommendation": f"ML accuracy at {ml_accuracy:.1f}% is marginal. "
                                  "Schedule retraining with latest data window.",
                "category": "Machine Learning",
            })

        ml_last_trained = ml.get("ml_last_trained")
        if ml_last_trained:
            try:
                trained_dt = datetime.fromisoformat(str(ml_last_trained))
                days_since = (datetime.now(timezone.utc) - trained_dt).days
                if days_since > 7:
                    recs.append({
                        "source": "ML Engineer",
                        "priority": "medium",
                        "recommendation": f"Models last trained {days_since} days ago. "
                                          "Weekly retraining recommended.",
                        "category": "Machine Learning",
                    })
            except (ValueError, TypeError):
                pass

        # ── From risk metrics ──
        risk = data.get("risk", {})
        drawdown = float(risk.get("drawdown", 0))
        if drawdown > 8:
            recs.append({
                "source": "Risk Manager",
                "priority": "critical",
                "recommendation": f"Drawdown at {drawdown:.1f}% approaching limit. "
                                  "Consider reducing position sizes or pausing new entries.",
                "category": "Risk Management",
            })
        elif drawdown > 5:
            recs.append({
                "source": "Risk Manager",
                "priority": "high",
                "recommendation": f"Drawdown at {drawdown:.1f}% is elevated. "
                                  "Monitor closely and review stop-loss levels.",
                "category": "Risk Management",
            })

        # ── From trading performance ──
        trading = data.get("trading", {})
        win_rate = float(trading.get("win_rate", 0))
        total_trades = int(trading.get("total_trades", 0))
        if total_trades > 10 and win_rate < 45:
            recs.append({
                "source": "Strategy Engineer",
                "priority": "high",
                "recommendation": f"Win rate at {win_rate:.1f}% over {total_trades} trades. "
                                  "Review entry criteria and conviction thresholds.",
                "category": "Strategy Performance",
            })

        profit_factor = trading.get("profit_factor")
        pf_below = (profit_factor is not None
                    and float(profit_factor) < 1.0 and total_trades > 5)
        if pf_below:
            recs.append({
                "source": "Strategy Engineer",
                "priority": "high",
                "recommendation": (
                    f"Profit factor {float(profit_factor):.2f} < 1.0 "
                    "indicates net loss. "
                    "Review risk:reward ratios and exit timing."
                ),
                "category": "Strategy Performance",
            })

        # ── From regime analysis ──
        regime = data.get("regime", {})
        dominant = regime.get("dominant_regime", "unknown")
        if dominant in ("strong_trend_down", "high_volatility"):
            recs.append({
                "source": "Market Analyst",
                "priority": "high",
                "recommendation": f"Market regime is {dominant.replace('_', ' ')}. "
                                  "Favor defensive strategies (BMR) and reduce position sizes.",
                "category": "Market Conditions",
            })

        # ── From news/sentiment ──
        news = data.get("news_intelligence", {})
        for ac, signal in news.get("sentiment_signal", {}).items():
            if isinstance(signal, dict):
                sig_val = float(signal.get("signal", 0))
                label = signal.get("signal_label", "neutral")
                if abs(sig_val) > 0.3:
                    recs.append({
                        "source": "Market Analyst",
                        "priority": "medium",
                        "recommendation": (
                            f"{ac.upper()} sentiment strongly {label} "
                            f"(score: {sig_val:.2f}). "
                            + ("Consider increasing exposure."
                               if sig_val > 0
                               else "Consider reducing exposure.")
                        ),
                        "category": "Sentiment",
                    })

        # ── From orchestrator state ──
        paused_strategies = [
            o for o in data.get("orchestrator", [])
            if str(o.get("action", "")).lower() in ("pause", "paused")
        ]
        if paused_strategies:
            names = ", ".join(o["strategy"] for o in paused_strategies)
            recs.append({
                "source": "Strategy Engineer",
                "priority": "info",
                "recommendation": f"Paused strategies: {names}. "
                                  "Review regime alignment before reactivation.",
                "category": "Strategy Orchestration",
            })

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        recs.sort(key=lambda r: priority_order.get(r.get("priority", "info"), 5))

        return recs

    @staticmethod
    def _generate_lessons_learned(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate 'what we learned today' narratives from data patterns."""
        lessons: list[dict[str, Any]] = []

        # ── Signal attribution lessons ──
        attribution = data.get("attribution", {})
        sources = attribution.get("sources", {})
        if sources:
            best_source = None
            worst_source = None
            best_acc = 0
            worst_acc = 100

            for name, src in sources.items():
                acc = float(src.get("accuracy", 0)) if isinstance(src, dict) else 0
                trades = int(src.get("trades", 0)) if isinstance(src, dict) else 0
                if trades >= 3:
                    if acc > best_acc:
                        best_acc = acc
                        best_source = name
                    if acc < worst_acc:
                        worst_acc = acc
                        worst_source = name

            if best_source:
                lessons.append({
                    "category": "Signal Intelligence",
                    "lesson": f"Best performing signal source: {best_source} "
                              f"({best_acc:.1f}% accuracy). "
                              "This source's predictions are providing reliable alpha.",
                    "impact": "positive",
                })

            if worst_source and worst_source != best_source:
                lessons.append({
                    "category": "Signal Intelligence",
                    "lesson": f"Weakest signal source: {worst_source} "
                              f"({worst_acc:.1f}% accuracy). "
                              "Consider reducing this source's weight in the composite signal.",
                    "impact": "negative",
                })

        # ── Strategy performance lessons ──
        strategies = data.get("strategy_breakdown", [])
        for strat in strategies:
            tc = int(strat.get("trade_count", 0) or 0)
            if tc > 0:
                wins = int(strat.get("winning_trades", 0) or 0)
                wr = (wins / tc * 100) if tc > 0 else 0
                pnl = float(strat.get("pnl", 0) or 0)
                name = strat.get("name", "Unknown")

                if wr >= 60 and pnl > 0:
                    lessons.append({
                        "category": "Strategy Performance",
                        "lesson": f"{name} performing well: {wr:.0f}% win rate, "
                                  f"${pnl:+.2f} P&L. Current parameters are effective.",
                        "impact": "positive",
                    })
                elif wr < 40 and tc >= 5:
                    lessons.append({
                        "category": "Strategy Performance",
                        "lesson": f"{name} underperforming: {wr:.0f}% win rate over "
                                  f"{tc} trades. Entry criteria may need tightening.",
                        "impact": "negative",
                    })

        # ── Regime transition lessons ──
        regime = data.get("regime", {})
        dominant = regime.get("dominant_regime", "unknown")
        confidence = regime.get("avg_confidence", 0)

        if confidence < 0.5 and dominant != "unknown":
            lessons.append({
                "category": "Market Structure",
                "lesson": f"Regime detection confidence is low ({confidence*100:.0f}%). "
                          "Market may be in transition. Multi-regime strategies "
                          "should use caution.",
                "impact": "warning",
            })

        # ── Sentiment-driven lessons ──
        news = data.get("news_intelligence", {})
        themes = news.get("top_themes", [])
        if themes:
            top_3 = ", ".join(themes[:3])
            lessons.append({
                "category": "Market Intelligence",
                "lesson": f"Dominant news themes today: {top_3}. "
                          "These themes are influencing sentiment signals.",
                "impact": "info",
            })

        # ── Risk lessons ──
        risk = data.get("risk", {})
        drawdown = float(risk.get("drawdown", 0))
        daily_pnl = float(risk.get("daily_pnl", 0))

        if drawdown > 5:
            lessons.append({
                "category": "Risk Management",
                "lesson": f"Drawdown reached {drawdown:.1f}% — the adaptive regime tightening "
                          "system has reduced position sizes. This protective measure "
                          "has historically limited further losses.",
                "impact": "warning",
            })

        if daily_pnl < -50:
            lessons.append({
                "category": "Risk Management",
                "lesson": f"Daily loss of ${abs(daily_pnl):.2f} recorded. "
                          "Reviewing what drove the loss helps identify "
                          "whether this was market-driven or strategy-driven.",
                "impact": "negative",
            })
        elif daily_pnl > 50:
            lessons.append({
                "category": "Risk Management",
                "lesson": f"Strong daily profit of ${daily_pnl:.2f}. "
                          "Identify which conditions and signals contributed "
                          "to capture this alpha.",
                "impact": "positive",
            })

        # ── Decision count lesson ──
        decisions = data.get("decisions", [])
        if decisions:
            lessons.append({
                "category": "Operations",
                "lesson": f"{len(decisions)} automated decisions were made in the last 24h. "
                          "Review the Decisions section for details on "
                          "orchestrator transitions and risk events.",
                "impact": "info",
            })

        return lessons


# ══════════════════════════════════════════════════════════════════════
# Helper functions for team assessments
# ══════════════════════════════════════════════════════════════════════

def _assess_quant(data: dict[str, Any]) -> dict[str, Any]:
    """Quantitative Developer assessment: signal quality and model performance."""
    findings = []
    concerns = []
    score = 70  # Baseline

    attribution = data.get("attribution", {})
    sources = attribution.get("sources", {})
    overall_wr = float(attribution.get("overall_win_rate", 0))
    total_trades = int(attribution.get("total_trades", 0))

    if total_trades > 0:
        findings.append(f"Signal system processed {total_trades} trades "
                        f"with {overall_wr:.1f}% overall win rate.")
        if overall_wr >= 55:
            score += 10
            findings.append(
                "Signal quality is above threshold "
                "— composite scoring is adding value."
            )
        elif overall_wr < 45:
            score -= 15
            concerns.append(f"Overall win rate {overall_wr:.1f}% is below breakeven. "
                            "Signal weights need rebalancing.")
    else:
        findings.append("No resolved trades in analysis window — signal quality unmeasurable.")
        score -= 5

    # Check source diversity
    active_sources = sum(1 for s in sources.values()
                         if isinstance(s, dict) and int(s.get("trades", 0)) > 0)
    findings.append(
        f"{active_sources} of {len(sources)} signal sources "
        "are contributing to trades."
    )
    if active_sources < 3:
        concerns.append(
            "Low source diversity. Need more signal sources "
            "contributing for robust composite."
        )
        score -= 10

    weights = data.get("weights", {})
    adjustments = weights.get("adjustments", {})
    large_adj = sum(1 for v in adjustments.values() if abs(float(v or 0)) > 0.03)
    if large_adj > 0:
        concerns.append(f"{large_adj} signal sources need significant weight adjustments.")
        score -= 5

    return {
        "title": "Quantitative Developer",
        "health_score": max(0, min(100, score)),
        "status": "good" if score >= 70 else ("warning" if score >= 50 else "critical"),
        "findings": findings,
        "concerns": concerns,
    }


def _assess_strategy(data: dict[str, Any]) -> dict[str, Any]:
    """Strategy Engineer assessment: strategy alignment and execution quality."""
    findings = []
    concerns = []
    score = 70

    strategies = data.get("strategy_breakdown", [])
    running = [s for s in strategies if s.get("running")]
    stopped = [s for s in strategies if not s.get("running")]

    findings.append(f"{len(running)} strategies running, {len(stopped)} stopped.")

    total_pnl = sum(float(s.get("pnl", 0)) for s in strategies)
    if total_pnl > 0:
        score += 10
        findings.append(f"Combined strategy P&L: +${total_pnl:.2f} — strategies are profitable.")
    elif total_pnl < 0:
        score -= 10
        concerns.append(
            f"Combined strategy P&L: -${abs(total_pnl):.2f} "
            "— net loss across strategies."
        )

    # Orchestrator alignment
    orchestrator = data.get("orchestrator", [])
    if orchestrator:
        avg_alignment = sum(float(o.get("alignment", 0)) for o in orchestrator) / len(orchestrator)
        findings.append(f"Average regime alignment: {avg_alignment:.0f}%.")
        if avg_alignment < 40:
            score -= 15
            concerns.append(
                "Low regime alignment. Strategies may be "
                "misaligned with current market conditions."
            )
        elif avg_alignment >= 70:
            score += 10

        paused = [
            o for o in orchestrator
            if str(o.get("action", "")).lower() in ("pause", "paused")
        ]
        if paused:
            names = ", ".join(o["strategy"] for o in paused)
            concerns.append(f"Paused strategies: {names}. Awaiting favorable regime conditions.")
            score -= 5

    if not running:
        score -= 20
        concerns.append("No strategies currently running. Trading is effectively halted.")

    return {
        "title": "Strategy Engineer",
        "health_score": max(0, min(100, score)),
        "status": "good" if score >= 70 else ("warning" if score >= 50 else "critical"),
        "findings": findings,
        "concerns": concerns,
    }


def _assess_risk(data: dict[str, Any]) -> dict[str, Any]:
    """Risk Manager assessment: drawdown, VaR, and risk controls."""
    findings = []
    concerns = []
    score = 80  # Risk starts high

    risk = data.get("risk", {})
    drawdown = float(risk.get("drawdown", 0))
    daily_pnl = float(risk.get("daily_pnl", 0))
    is_halted = risk.get("is_halted", False)
    equity = float(risk.get("equity", 0))
    peak = float(risk.get("peak_equity", 0))

    findings.append(f"Equity: ${equity:,.2f} | Peak: ${peak:,.2f} | Drawdown: {drawdown:.1f}%.")

    if is_halted:
        score -= 30
        concerns.append(f"TRADING HALTED: {risk.get('halt_reason', 'Unknown reason')}.")
    elif drawdown > 8:
        score -= 25
        concerns.append(f"Drawdown at {drawdown:.1f}% — approaching critical threshold.")
    elif drawdown > 5:
        score -= 10
        concerns.append(f"Drawdown elevated at {drawdown:.1f}% — monitoring closely.")
    else:
        findings.append("Drawdown within normal parameters.")

    if daily_pnl < 0:
        findings.append(f"Daily P&L: -${abs(daily_pnl):.2f}.")
        if daily_pnl < -100:
            score -= 15
            concerns.append("Significant daily loss — risk limits may need tightening.")
    else:
        findings.append(f"Daily P&L: +${daily_pnl:.2f}.")
        score += 5

    var_95 = float(risk.get("var_95", 0))
    if var_95 > 0:
        findings.append(f"Value at Risk (95%): ${var_95:,.2f} 1-day horizon.")

    return {
        "title": "Risk Manager",
        "health_score": max(0, min(100, score)),
        "status": "good" if score >= 70 else ("warning" if score >= 50 else "critical"),
        "findings": findings,
        "concerns": concerns,
    }


def _assess_data(data: dict[str, Any]) -> dict[str, Any]:
    """Data Engineer assessment: data quality, pipeline health, coverage."""
    findings = []
    concerns = []
    score = 75

    system = data.get("system", {})
    scheduler_running = system.get("scheduler_running", False)
    jobs_failed = int(system.get("total_jobs_failed", 0))
    jobs_completed = int(system.get("total_jobs_completed", 0))

    if scheduler_running:
        findings.append("Scheduler is running — data pipeline is active.")
    else:
        score -= 20
        concerns.append("Scheduler is NOT running — data pipeline may be stalled.")

    if jobs_completed > 0:
        total_jobs = jobs_completed + jobs_failed
        failure_rate = (
            jobs_failed / total_jobs * 100 if total_jobs > 0 else 0
        )
        findings.append(f"Job completion: {jobs_completed} completed, {jobs_failed} failed "
                        f"({failure_rate:.1f}% failure rate).")
        if failure_rate > 10:
            score -= 15
            concerns.append(f"High job failure rate ({failure_rate:.1f}%). "
                            "Check data source connectivity.")
        elif failure_rate > 5:
            score -= 5

    # Check equity history data density
    equity_history = data.get("equity_history", [])
    if equity_history:
        findings.append(f"{len(equity_history)} equity snapshots in analysis window.")
    else:
        concerns.append("No equity history data available — portfolio tracking may be stalled.")
        score -= 10

    # Check if we have recent data
    last_refresh = system.get("last_data_refresh")
    if last_refresh:
        findings.append(f"Last data refresh: {last_refresh}.")
    else:
        concerns.append("Unable to determine when data was last refreshed.")
        score -= 5

    return {
        "title": "Data Engineer",
        "health_score": max(0, min(100, score)),
        "status": "good" if score >= 70 else ("warning" if score >= 50 else "critical"),
        "findings": findings,
        "concerns": concerns,
    }


def _assess_ml(data: dict[str, Any]) -> dict[str, Any]:
    """ML Engineer assessment: model accuracy, staleness, feature health."""
    findings = []
    concerns = []
    score = 65  # ML starts cautious

    ml = data.get("ml", {})
    accuracy = ml.get("ml_accuracy") or 0
    models_count = int(ml.get("ml_models_count", 0))
    predictions = int(ml.get("ml_predictions_total", 0))
    last_trained = ml.get("ml_last_trained")

    if models_count > 0:
        findings.append(f"{models_count} models active, {predictions} total predictions.")
    else:
        findings.append("No ML models currently active.")
        score -= 10

    if accuracy > 0:
        findings.append(f"Average model accuracy: {accuracy:.1f}%.")
        if accuracy >= 58:
            score += 15
            findings.append("Model accuracy is strong — ML signal is adding value.")
        elif accuracy >= 55:
            score += 10
        elif accuracy >= 52:
            score += 5
            concerns.append("Model accuracy is marginal. Close to random performance.")
        else:
            score -= 15
            concerns.append(f"Model accuracy {accuracy:.1f}% is below profitable threshold. "
                            "Consider disabling ML signal or retraining.")

    if last_trained:
        try:
            trained_dt = datetime.fromisoformat(str(last_trained))
            days_since = (datetime.now(timezone.utc) - trained_dt).days
            findings.append(f"Models last trained {days_since} days ago.")
            if days_since > 14:
                score -= 15
                concerns.append(f"Models are {days_since} days stale. Urgent retraining needed.")
            elif days_since > 7:
                score -= 5
                concerns.append("Models approaching staleness. Schedule retraining.")
        except (ValueError, TypeError):
            pass
    else:
        concerns.append("No training timestamp available.")

    return {
        "title": "ML Engineer",
        "health_score": max(0, min(100, score)),
        "status": "good" if score >= 70 else ("warning" if score >= 50 else "critical"),
        "findings": findings,
        "concerns": concerns,
    }


def _assess_market(data: dict[str, Any]) -> dict[str, Any]:
    """Market Analyst assessment: regime conditions, sentiment, opportunities."""
    findings = []
    concerns = []
    score = 70

    regime = data.get("regime", {})
    dominant = regime.get("dominant_regime", "unknown")
    confidence = regime.get("avg_confidence", 0)
    symbols_analyzed = regime.get("symbols_analyzed", 0)

    findings.append(f"Dominant regime: {dominant.replace('_', ' ').title()} "
                    f"(confidence: {confidence*100:.0f}%, {symbols_analyzed} symbols).")

    if dominant in ("strong_trend_up", "weak_trend_up"):
        score += 10
        findings.append("Bullish market structure — favorable for trend-following strategies.")
    elif dominant == "ranging":
        findings.append("Ranging market — mean reversion strategies are favored.")
    elif dominant in ("strong_trend_down",):
        score -= 15
        concerns.append("Strong bearish regime detected. Defensive posture recommended.")
    elif dominant == "high_volatility":
        score -= 10
        concerns.append("High volatility regime — increased uncertainty and risk.")

    if confidence < 0.5:
        score -= 10
        concerns.append("Low regime confidence suggests market transition. Use caution.")

    # Opportunities
    opportunities = data.get("opportunities", [])
    if opportunities:
        high_score = [o for o in opportunities if float(o.get("score", 0)) >= 80]
        findings.append(f"{len(opportunities)} active opportunities "
                        f"({len(high_score)} high-quality score >= 80).")
    else:
        findings.append("No active market opportunities detected by scanner.")

    # Sentiment
    news = data.get("news_intelligence", {})
    for ac, signal in news.get("sentiment_signal", {}).items():
        if isinstance(signal, dict):
            label = signal.get("signal_label", "neutral")
            sig_val = float(signal.get("signal", 0))
            findings.append(f"{ac.upper()} sentiment: {label} ({sig_val:+.2f}).")

    themes = news.get("top_themes", [])
    if themes:
        findings.append(f"Key news themes: {', '.join(themes[:3])}.")

    return {
        "title": "Market Analyst",
        "health_score": max(0, min(100, score)),
        "status": "good" if score >= 70 else ("warning" if score >= 50 else "critical"),
        "findings": findings,
        "concerns": concerns,
    }


def _categorize_decision(event_type: str) -> str:
    """Map event types to human-readable decision categories."""
    categories = {
        "orchestrator_transition": "Strategy Orchestration",
        "risk_halt": "Risk Management",
        "risk_resume": "Risk Management",
        "kill_switch_activated": "Emergency Action",
        "kill_switch_deactivated": "Emergency Action",
        "risk_warning": "Risk Management",
        "strategy_paused": "Strategy Orchestration",
        "strategy_resumed": "Strategy Orchestration",
        "auto_halt": "Risk Management",
        "drawdown_warning": "Risk Management",
        "daily_loss_warning": "Risk Management",
        "risk_limit_change": "Risk Management",
    }
    return categories.get(event_type, "System")


def _extract_themes(articles: list[dict[str, Any]]) -> list[str]:
    """Extract top news themes from article titles using keyword frequency."""
    if not articles:
        return []

    # Common financial/crypto keywords to look for
    theme_keywords = {
        "bitcoin": "Bitcoin", "btc": "Bitcoin", "ethereum": "Ethereum", "eth": "Ethereum",
        "fed": "Federal Reserve", "federal reserve": "Federal Reserve",
        "inflation": "Inflation", "cpi": "Inflation",
        "interest rate": "Interest Rates",
        "rate hike": "Interest Rates", "rate cut": "Interest Rates",
        "regulation": "Regulation", "sec": "Regulation", "regulatory": "Regulation",
        "etf": "ETF Activity", "spot etf": "ETF Activity",
        "earnings": "Earnings", "revenue": "Earnings",
        "recession": "Recession Risk", "gdp": "Economic Growth",
        "defi": "DeFi", "nft": "NFTs",
        "halving": "Bitcoin Halving", "mining": "Crypto Mining",
        "stablecoin": "Stablecoins", "usdt": "Stablecoins", "usdc": "Stablecoins",
        "exchange": "Exchange News", "binance": "Exchange News", "kraken": "Exchange News",
        "hack": "Security", "exploit": "Security", "vulnerability": "Security",
        "whale": "Whale Activity", "liquidation": "Liquidations",
        "rally": "Price Rally", "crash": "Price Crash", "dump": "Price Crash",
        "bull": "Bullish Sentiment", "bear": "Bearish Sentiment",
        "forex": "Forex", "dollar": "US Dollar", "dxy": "US Dollar",
        "oil": "Oil/Energy", "gold": "Gold",
        "tariff": "Trade Policy", "trade war": "Trade Policy",
    }

    theme_counts: dict[str, int] = defaultdict(int)
    for article in articles:
        title = str(article.get("title", "")).lower()
        counted_themes: set[str] = set()
        for keyword, theme in theme_keywords.items():
            if keyword in title and theme not in counted_themes:
                theme_counts[theme] += 1
                counted_themes.add(theme)

    # Sort by frequency and return top themes
    sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)
    return [theme for theme, _count in sorted_themes[:5]]
