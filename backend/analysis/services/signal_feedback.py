"""Signal Feedback Service — Django layer for performance tracking and adaptive tuning.

Bridges the common.signals feedback/tracker with Django ORM persistence
and provides methods for API views and task executors.
"""

import logging
from datetime import timedelta
from typing import Any

import requests
from django.utils import timezone as tz

from core.platform_bridge import ensure_platform_imports

logger = logging.getLogger(__name__)


class SignalFeedbackService:
    """Django-side service for signal attribution and feedback."""

    @staticmethod
    def record_attribution(
        order_id: str,
        symbol: str,
        asset_class: str,
        strategy: str,
        signal_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Record signal attribution at trade entry.

        Args:
            order_id: The order being entered.
            symbol: Trading symbol.
            asset_class: crypto/equity/forex.
            strategy: Strategy name.
            signal_data: Dict from SignalService.get_signal() with components.

        Returns:
            Dict with the created attribution record.

        """
        from analysis.models import SignalAttribution

        components = signal_data.get("components", {})
        # Extract regime name from the cached _regime key or confidences
        entry_regime = signal_data.get("_regime", "") or ""
        attr = SignalAttribution.objects.create(
            order_id=order_id,
            symbol=symbol,
            asset_class=asset_class,
            strategy=strategy,
            composite_score=signal_data.get("composite_score", 0.0),
            technical_contribution=components.get("technical", 0.0),
            ml_contribution=components.get("ml", 0.0),
            sentiment_contribution=components.get("sentiment", 0.0),
            regime_contribution=components.get("regime", 0.0),
            scanner_contribution=components.get("scanner", 0.0),
            screen_contribution=components.get("scanner", 0.0),
            win_rate_contribution=components.get("win_rate", 0.0),
            position_modifier=signal_data.get("position_modifier", 1.0),
            entry_regime=entry_regime,
        )
        logger.info("Signal attribution recorded: order=%s symbol=%s", order_id[:8], symbol)
        return {
            "id": str(attr.id),
            "order_id": attr.order_id,
            "symbol": attr.symbol,
            "composite_score": attr.composite_score,
        }

    @staticmethod
    def backfill_outcomes(window_hours: int = 24) -> dict[str, Any]:
        """Match open attributions with completed orders and backfill outcomes.

        Looks for SignalAttribution records with outcome='open' that have
        matching filled orders and updates their outcome/pnl.

        Returns:
            Dict with counts of resolved records.

        """
        from analysis.models import SignalAttribution

        cutoff = tz.now() - timedelta(hours=window_hours)
        open_attrs = SignalAttribution.objects.filter(
            outcome="open",
            recorded_at__gte=cutoff,
        )[:200]

        resolved = 0
        for attr in open_attrs:
            try:
                from trading.models import Order

                order = Order.objects.filter(
                    id=attr.order_id,
                    status="filled",
                ).first()
                if order is None:
                    continue

                # Determine outcome from P&L
                pnl = _compute_pnl(order)
                outcome = "win" if pnl is not None and pnl > 0 else "loss"

                attr.outcome = outcome
                attr.pnl = pnl
                attr.resolved_at = tz.now()
                attr.save(update_fields=["outcome", "pnl", "resolved_at"])
                resolved += 1
            except Exception as e:
                logger.warning("Backfill failed for attr %s: %s", attr.id, e)

        logger.info("Backfilled %d attribution outcomes", resolved)
        return {"resolved": resolved, "checked": len(open_attrs)}

    @staticmethod
    def backfill_from_freqtrade(window_hours: int = 24) -> dict[str, Any]:
        """Backfill ML prediction outcomes from Freqtrade closed trades.

        Queries all Freqtrade instances for recently closed trades, then matches
        them to MLPrediction records by symbol and time proximity.

        Args:
            window_hours: How far back to look for closed trades.

        Returns:
            Dict with matched, unmatched, and error counts.
        """
        from django.conf import settings

        from analysis.models import MLPrediction

        ft_instances = getattr(settings, "FREQTRADE_INSTANCES", [])
        ft_user = getattr(settings, "FREQTRADE_USERNAME", "freqtrader")
        ft_pass = getattr(settings, "FREQTRADE_PASSWORD", "freqtrader")

        matched = 0
        unmatched = 0
        errors = 0

        for instance in ft_instances:
            url = instance.get("url", "")
            if not url:
                continue

            try:
                resp = requests.get(
                    f"{url}/api/v1/trades",
                    auth=(ft_user, ft_pass),
                    params={"limit": 50},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                trades = data.get("trades", [])

                for trade in trades:
                    if not trade.get("close_date"):
                        continue  # Still open

                    symbol = trade.get("pair", "")
                    profit_ratio = trade.get("profit_ratio", 0.0)
                    actual_direction = "up" if profit_ratio > 0 else "down"

                    # Find matching MLPrediction by symbol within window
                    cutoff = tz.now() - timedelta(hours=window_hours)
                    prediction = (
                        MLPrediction.objects.filter(
                            symbol=symbol,
                            correct__isnull=True,
                            predicted_at__gte=cutoff,
                        )
                        .order_by("-predicted_at")
                        .first()
                    )

                    if prediction:
                        prediction.actual_direction = actual_direction
                        prediction.correct = prediction.direction == actual_direction
                        prediction.save(update_fields=["actual_direction", "correct"])
                        matched += 1
                    else:
                        unmatched += 1

            except Exception as e:
                logger.warning("Freqtrade trade fetch failed for %s: %s", url, e)
                errors += 1

        logger.info(
            "Freqtrade backfill: matched=%d, unmatched=%d, errors=%d",
            matched, unmatched, errors,
        )
        return {"matched": matched, "unmatched": unmatched, "errors": errors}

    @staticmethod
    def get_source_accuracy(
        asset_class: str | None = None,
        strategy: str | None = None,
        window_days: int = 30,
    ) -> dict[str, Any]:
        """Compute per-source accuracy from resolved SignalAttribution records.

        Returns accuracy stats for each signal source (ml, sentiment, regime, etc).
        """
        from django.db.models import Avg

        from analysis.models import SignalAttribution

        cutoff = tz.now() - timedelta(days=window_days)
        qs = SignalAttribution.objects.filter(
            outcome__in=["win", "loss"],
            recorded_at__gte=cutoff,
        )
        if asset_class:
            qs = qs.filter(asset_class=asset_class)
        if strategy:
            qs = qs.filter(strategy=strategy)

        total = qs.count()
        wins = qs.filter(outcome="win").count()
        win_rate = wins / total if total > 0 else 0.0

        # Per-source average scores for wins vs losses
        sources = ["technical", "ml", "sentiment", "regime", "scanner", "win_rate"]
        source_stats: dict[str, Any] = {}

        for src in sources:
            field_name = f"{src}_contribution"
            win_avg = qs.filter(outcome="win").aggregate(
                avg=Avg(field_name),
            )["avg"]
            loss_avg = qs.filter(outcome="loss").aggregate(
                avg=Avg(field_name),
            )["avg"]
            src_total = qs.filter(**{f"{field_name}__gt": 0}).count()
            src_wins = qs.filter(**{f"{field_name}__gt": 0}, outcome="win").count()

            source_stats[src] = {
                "total_trades": src_total,
                "wins": src_wins,
                "win_rate": src_wins / src_total if src_total > 0 else 0.0,
                "avg_score_win": round(win_avg or 0.0, 2),
                "avg_score_loss": round(loss_avg or 0.0, 2),
            }

        return {
            "total_trades": total,
            "wins": wins,
            "overall_win_rate": round(win_rate, 4),
            "window_days": window_days,
            "asset_class": asset_class,
            "strategy": strategy,
            "sources": source_stats,
        }

    @staticmethod
    def get_weight_recommendations(
        asset_class: str | None = None,
        strategy: str | None = None,
        window_days: int = 30,
    ) -> dict[str, Any]:
        """Compute adaptive weight recommendations based on trade outcomes.

        Uses the PerformanceFeedback engine from common.signals.
        """
        try:
            ensure_platform_imports()
            from common.signals.feedback import PerformanceFeedback
            from common.signals.performance_tracker import PerformanceTracker

            # Build tracker from DB records
            tracker = PerformanceTracker()
            _load_tracker_from_db(tracker, asset_class, strategy, window_days)

            feedback = PerformanceFeedback(tracker=tracker)
            adj = feedback.compute_weight_adjustments(
                asset_class=asset_class,
                strategy=strategy,
                window_days=window_days,
            )

            return {
                "current_weights": adj.current_weights,
                "recommended_weights": adj.recommended_weights,
                "adjustments": adj.adjustments,
                "source_accuracy": adj.source_accuracy,
                "total_trades": adj.total_trades,
                "win_rate": round(adj.win_rate, 4),
                "threshold_adjustment": adj.threshold_adjustment,
                "reasoning": adj.reasoning,
            }
        except Exception as e:
            logger.warning("Weight recommendation failed: %s", e)
            return {"error": str(e)}


def _compute_pnl(order) -> float | None:
    """Compute P&L for a filled order by finding the matching closing order.

    Looks for a corresponding filled order on the opposite side for the same
    symbol. Excludes orders already matched to other attributions to avoid
    cross-contamination between trades.
    """
    try:
        from trading.models import Order

        from analysis.models import SignalAttribution

        if not order.avg_fill_price or order.avg_fill_price <= 0:
            return None

        close_side = "sell" if order.side == "buy" else "buy"

        # Find already-matched order IDs to exclude them
        already_matched = set(
            SignalAttribution.objects.filter(
                outcome__in=["win", "loss"],
            ).values_list("order_id", flat=True)
        )

        close_candidates = Order.objects.filter(
            symbol=order.symbol,
            side=close_side,
            status="filled",
            portfolio_id=order.portfolio_id,
            filled_at__gte=order.filled_at or order.timestamp,
        ).order_by("filled_at")

        close_order = None
        for candidate in close_candidates[:10]:
            if str(candidate.id) not in already_matched:
                close_order = candidate
                break

        if close_order is None or not close_order.avg_fill_price:
            return None

        if order.side == "buy":
            pnl = (close_order.avg_fill_price - order.avg_fill_price) * order.filled
        else:
            pnl = (order.avg_fill_price - close_order.avg_fill_price) * order.filled
        return round(pnl - order.fee - close_order.fee, 4)
    except Exception:
        return None


def _load_tracker_from_db(
    tracker,
    asset_class: str | None,
    strategy: str | None,
    window_days: int,
) -> None:
    """Load SignalAttribution records from DB into the in-memory tracker."""
    from analysis.models import SignalAttribution

    cutoff = tz.now() - timedelta(days=window_days)
    qs = SignalAttribution.objects.filter(recorded_at__gte=cutoff)
    if asset_class:
        qs = qs.filter(asset_class=asset_class)
    if strategy:
        qs = qs.filter(strategy=strategy)

    for attr in qs[:500]:
        contributions = {
            "technical": attr.technical_contribution,
            "ml": attr.ml_contribution,
            "sentiment": attr.sentiment_contribution,
            "regime": attr.regime_contribution,
            "scanner": attr.scanner_contribution,
            "win_rate": attr.win_rate_contribution,
        }
        tracker.record_entry(
            order_id=attr.order_id,
            symbol=attr.symbol,
            asset_class=attr.asset_class,
            strategy=attr.strategy,
            composite_score=attr.composite_score,
            contributions=contributions,
            position_modifier=attr.position_modifier,
            entry_regime=attr.entry_regime,
        )
        if attr.outcome != "open":
            tracker.record_outcome(
                order_id=attr.order_id,
                outcome=attr.outcome,
                pnl=attr.pnl,
            )
