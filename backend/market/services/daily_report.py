"""DailyReportService — generates daily intelligence summaries.

Aggregates market regime, top opportunities, data coverage, strategy
performance, and system readiness into a single JSON report.
"""

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


class DailyReportService:
    """Generate and store daily intelligence reports."""

    def generate(self) -> dict[str, Any]:
        """Build the daily report. Returns the report dict."""
        now = timezone.now()
        report: dict[str, Any] = {
            "generated_at": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
        }

        report["regime"] = self._get_regime_summary()
        report["top_opportunities"] = self._get_top_opportunities()
        report["data_coverage"] = self._get_data_coverage()
        report["strategy_performance"] = self._get_strategy_performance()
        report["system_status"] = self._get_system_status()
        report["scanner_status"] = self._get_scanner_status()
        report["recommendations"] = self._get_recommendations(report["regime"])

        # Store in DB as a special MarketOpportunity-like record
        # or just return for API consumption
        return report

    @staticmethod
    def _get_regime_summary() -> dict[str, Any]:
        """Current market regime for crypto and top forex symbols."""
        try:
            from core.platform_bridge import ensure_platform_imports, get_platform_config

            ensure_platform_imports()

            from market.services.regime import RegimeService

            config = get_platform_config()
            data_cfg = config.get("data", {})

            # Crypto symbols (default) + top 5 forex pairs
            crypto_symbols = data_cfg.get("watchlist", [])[:10]
            forex_symbols = data_cfg.get("forex_watchlist", [])[:5]
            all_symbols = crypto_symbols + forex_symbols

            service = RegimeService(symbols=all_symbols)
            regimes = service.get_all_current_regimes()
            if not regimes:
                return {"status": "no_data", "regimes": []}

            # Count regime distribution
            distribution: dict[str, int] = {}
            for r in regimes:
                regime = r.get("regime", "unknown")
                distribution[regime] = distribution.get(regime, 0) + 1

            avg_confidence = sum(r.get("confidence", 0) for r in regimes) / len(regimes)

            return {
                "status": "ok",
                "symbols_analyzed": len(regimes),
                "distribution": distribution,
                "avg_confidence": round(avg_confidence, 2),
                "dominant_regime": max(distribution, key=distribution.get)
                if distribution
                else "unknown",
            }
        except Exception as e:
            logger.warning("Regime summary failed: %s", e)
            return {"status": "error", "error": str(e)}

    @staticmethod
    def _get_top_opportunities() -> list[dict[str, Any]]:
        """Top 5 active opportunities by score."""
        try:
            from market.models import MarketOpportunity

            now = timezone.now()
            opps = MarketOpportunity.objects.filter(
                expires_at__gt=now,
            ).order_by("-score")[:5]

            return [
                {
                    "symbol": o.symbol,
                    "type": o.opportunity_type,
                    "score": o.score,
                    "details": o.details,
                    "detected_at": o.detected_at.isoformat(),
                }
                for o in opps
            ]
        except Exception as e:
            logger.warning("Top opportunities failed: %s", e)
            return []

    @staticmethod
    def _get_data_coverage() -> dict[str, Any]:
        """How many pairs have data, freshness stats across all asset classes."""
        try:
            from core.platform_bridge import ensure_platform_imports, get_platform_config

            ensure_platform_imports()
            from common.data_pipeline.pipeline import list_available_data

            config = get_platform_config()
            data_cfg = config.get("data", {})

            watchlist_keys = {
                "crypto": "watchlist",
                "equity": "equity_watchlist",
                "forex": "forex_watchlist",
            }
            all_symbols: list[str] = []
            per_asset_class: dict[str, dict[str, Any]] = {}
            for ac, key in watchlist_keys.items():
                symbols = data_cfg.get(key, [])
                all_symbols.extend(symbols)
                per_asset_class[ac] = {"total_pairs": len(symbols)}

            total_pairs = len(all_symbols)

            available = list_available_data()
            if available.empty:
                for ac in per_asset_class:
                    per_asset_class[ac]["pairs_with_data"] = 0
                    per_asset_class[ac]["coverage_pct"] = 0
                return {
                    "total_pairs": total_pairs,
                    "pairs_with_data": 0,
                    "coverage_pct": 0,
                    "per_asset_class": per_asset_class,
                }

            available_symbols = (
                set(available["symbol"].unique()) if "symbol" in available.columns else set()
            )
            pairs_with_data = len(available_symbols & set(all_symbols))

            for ac, key in watchlist_keys.items():
                ac_symbols = set(data_cfg.get(key, []))
                ac_covered = len(available_symbols & ac_symbols)
                per_asset_class[ac]["pairs_with_data"] = ac_covered
                per_asset_class[ac]["coverage_pct"] = round(
                    ac_covered / max(len(ac_symbols), 1) * 100, 1,
                )

            return {
                "total_pairs": total_pairs,
                "pairs_with_data": pairs_with_data,
                "coverage_pct": round(pairs_with_data / max(total_pairs, 1) * 100, 1),
                "total_files": len(available),
                "per_asset_class": per_asset_class,
            }
        except Exception as e:
            logger.warning("Data coverage check failed: %s", e)
            return {"total_pairs": 0, "pairs_with_data": 0, "coverage_pct": 0, "error": str(e)}

    @staticmethod
    def _get_strategy_performance() -> dict[str, Any]:
        """Aggregate P&L and stats from paper trading."""
        try:
            from trading.models import Order, OrderStatus, TradingMode

            now = timezone.now()
            last_24h = now - timedelta(hours=24)

            total_orders = Order.objects.filter(mode=TradingMode.PAPER).count()
            recent_orders = Order.objects.filter(
                mode=TradingMode.PAPER,
                created_at__gte=last_24h,
            ).count()

            filled_orders = Order.objects.filter(
                mode=TradingMode.PAPER,
                status=OrderStatus.FILLED,
            )
            total_filled = filled_orders.count()

            # Calculate win rate from filled orders
            wins = 0
            losses = 0
            total_pnl = 0.0
            for order in filled_orders:
                pnl = getattr(order, "realized_pnl", 0) or 0
                total_pnl += pnl
                if pnl > 0:
                    wins += 1
                elif pnl < 0:
                    losses += 1

            win_rate = wins / max(wins + losses, 1) * 100

            return {
                "total_orders": total_orders,
                "recent_orders_24h": recent_orders,
                "filled_orders": total_filled,
                "win_rate": round(win_rate, 1),
                "total_pnl": round(total_pnl, 2),
            }
        except Exception as e:
            logger.warning("Strategy performance failed: %s", e)
            return {"total_orders": 0, "error": str(e)}

    @staticmethod
    def _get_system_status() -> dict[str, Any]:
        """Paper trading duration, data baseline status."""
        try:
            from trading.models import Order, TradingMode

            # Find earliest paper trade to compute days in paper trading
            earliest = (
                Order.objects.filter(mode=TradingMode.PAPER)
                .order_by("created_at")
                .values_list("created_at", flat=True)
                .first()
            )

            now = timezone.now()
            days_trading = (now - earliest).days if earliest else 0

            min_days = 14
            if days_trading >= min_days:
                readiness = "Ready: regime calibrated, data baseline established"
            else:
                readiness = f"Gathering baseline data (day {days_trading}/{min_days})"

            return {
                "days_paper_trading": days_trading,
                "min_days_required": min_days,
                "readiness": readiness,
                "is_ready": days_trading >= min_days,
            }
        except Exception as e:
            logger.warning("System status check failed: %s", e)
            return {"days_paper_trading": 0, "readiness": "unknown", "error": str(e)}

    @staticmethod
    def _get_scanner_status() -> dict[str, Any]:
        """Last-run info for market scanner scheduled tasks."""
        try:
            from core.models import ScheduledTask

            result: dict[str, Any] = {}
            for task_id in ("market_scan_crypto", "market_scan_forex"):
                try:
                    task = ScheduledTask.objects.get(id=task_id)
                    result[task_id] = {
                        "task_id": task_id,
                        "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
                        "last_run_status": task.last_run_status,
                        "run_count": task.run_count,
                        "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                    }
                except ScheduledTask.DoesNotExist:
                    result[task_id] = {
                        "task_id": task_id,
                        "last_run_at": None,
                        "last_run_status": None,
                        "run_count": 0,
                        "next_run_at": None,
                    }
            return result
        except Exception as e:
            logger.warning("Scanner status failed: %s", e)
            return {}

    @staticmethod
    def _get_recommendations(regime_data: dict[str, Any]) -> dict[str, Any]:
        """Map current regime to strategy recommendations."""
        regime_strategy_map = {
            "strong_trend_up": {
                "primary": "CryptoInvestorV1",
                "reasoning": "Strong uptrend — trend-following strategies favored",
            },
            "weak_trend_up": {
                "primary": "CryptoInvestorV1",
                "reasoning": "Weak uptrend — trend-following with tighter stops",
            },
            "ranging": {
                "primary": "BollingerMeanReversion",
                "reasoning": "Range-bound market — mean reversion strategies favored",
            },
            "weak_trend_down": {
                "primary": "BollingerMeanReversion",
                "reasoning": "Weak downtrend — oversold bounces likely, BMR strategy favored",
            },
            "strong_trend_down": {
                "primary": "BollingerMeanReversion",
                "reasoning": "Strong downtrend — defensive positioning, catch oversold bounces",
            },
            "high_volatility": {
                "primary": "VolatilityBreakout",
                "reasoning": "High volatility — breakout strategies capture expansion moves",
            },
            "unknown": {
                "primary": "BollingerMeanReversion",
                "reasoning": "Regime unclear — defaulting to defensive mean reversion",
            },
        }

        dominant = regime_data.get("dominant_regime", "unknown")
        rec = regime_strategy_map.get(dominant, regime_strategy_map["unknown"])

        # Add sentiment direction if available
        sentiment_text = "No sentiment data"
        try:
            from django.utils import timezone as tz

            from market.models import NewsArticle

            recent = NewsArticle.objects.filter(
                published_at__gte=tz.now() - timedelta(hours=24),
            )
            if recent.exists():
                avg_score = sum(a.sentiment_score for a in recent) / recent.count()
                if avg_score > 0.15:
                    sentiment_text = "Sentiment bullish — supports aggressive entries"
                elif avg_score < -0.15:
                    sentiment_text = "Sentiment bearish — favor defensive strategies"
                else:
                    sentiment_text = "Sentiment neutral"
        except Exception:
            pass

        return {
            "regime": dominant,
            "favored_strategy": rec["primary"],
            "reasoning": rec["reasoning"],
            "sentiment": sentiment_text,
        }

    def get_latest(self) -> dict[str, Any] | None:
        """Return the most recent stored report, or generate fresh."""
        # For simplicity, always generate fresh — reports are cheap
        return self.generate()

    def get_history(self, limit: int = 30) -> list[dict[str, Any]]:
        """Return recent reports. For now, returns just the latest."""
        # Future: store reports in DB for historical access
        report = self.generate()
        return [report]
