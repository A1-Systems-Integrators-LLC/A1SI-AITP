"""Performance feedback — adaptive weight tuning based on trade outcomes.

Analyzes which signal sources contribute to winning vs losing trades
and adjusts weights accordingly. Also adapts conviction thresholds
based on overall win rate.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from common.signals.constants import DEFAULT_WEIGHTS
from common.signals.performance_tracker import PerformanceTracker, SourceAccuracy

logger = logging.getLogger("signal_feedback")

# Bounds for adaptive adjustments
MIN_WEIGHT = 0.02  # Never drop a source below 2%
MAX_WEIGHT = 0.50  # Never exceed 50% for any source
WEIGHT_ADJUSTMENT_RATE = 0.05  # Max per-cycle adjustment
THRESHOLD_ADJUSTMENT_UP = 5  # Raise threshold when losing
THRESHOLD_ADJUSTMENT_DOWN = 3  # Lower threshold when winning
THRESHOLD_FLOOR = 50
THRESHOLD_CEILING = 80
MIN_TRADES_FOR_ADJUSTMENT = 10  # Need at least this many resolved trades


@dataclass
class WeightAdjustment:
    """Result of adaptive weight computation."""

    current_weights: dict[str, float]
    recommended_weights: dict[str, float]
    adjustments: dict[str, float]  # per-source delta
    source_accuracy: dict[str, float]  # per-source win rate
    total_trades: int = 0
    win_rate: float = 0.0
    threshold_adjustment: int = 0  # delta to apply to conviction threshold
    reasoning: list[str] = field(default_factory=list)


class PerformanceFeedback:
    """Computes adaptive weight adjustments based on signal attribution outcomes.

    Thread-safe via threading.Lock.

    Usage:
        tracker = PerformanceTracker()
        feedback = PerformanceFeedback(tracker)
        adj = feedback.compute_weight_adjustments()
        # adj.recommended_weights contains new weights
        # adj.threshold_adjustment contains threshold delta
    """

    def __init__(
        self,
        tracker: PerformanceTracker | None = None,
        base_weights: dict[str, float] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._tracker = tracker or PerformanceTracker()
        self._base_weights = dict(base_weights or DEFAULT_WEIGHTS)
        self._current_weights = dict(self._base_weights)
        self._threshold_delta = 0

    @property
    def current_weights(self) -> dict[str, float]:
        with self._lock:
            return dict(self._current_weights)

    @property
    def threshold_delta(self) -> int:
        with self._lock:
            return self._threshold_delta

    def compute_weight_adjustments(
        self,
        asset_class: str | None = None,
        strategy: str | None = None,
        window_days: int = 30,
    ) -> WeightAdjustment:
        """Analyze recent trade outcomes and compute recommended weight changes.

        Args:
            asset_class: Filter trades by asset class.
            strategy: Filter trades by strategy.
            window_days: Lookback window for trades.

        Returns:
            WeightAdjustment with current, recommended, and delta weights.
        """
        source_acc = self._tracker.get_source_accuracy(
            asset_class=asset_class,
            strategy=strategy,
            window_days=window_days,
        )

        # Compute overall stats from tracker records
        records = self._tracker.get_records(asset_class=asset_class, limit=500)
        resolved = [r for r in records if r.outcome != "open"]
        total = len(resolved)
        wins = sum(1 for r in resolved if r.outcome == "win")
        win_rate = wins / total if total > 0 else 0.0

        reasoning: list[str] = []

        with self._lock:
            current = dict(self._current_weights)

        if total < MIN_TRADES_FOR_ADJUSTMENT:
            reasoning.append(
                f"Only {total} resolved trades (need {MIN_TRADES_FOR_ADJUSTMENT}). "
                "Keeping current weights."
            )
            return WeightAdjustment(
                current_weights=current,
                recommended_weights=dict(current),
                adjustments={k: 0.0 for k in current},
                source_accuracy={s: a.win_rate for s, a in source_acc.items()},
                total_trades=total,
                win_rate=win_rate,
                threshold_adjustment=0,
                reasoning=reasoning,
            )

        # ── Compute per-source adjustments ──────────────────────────
        recommended = dict(current)
        adjustments: dict[str, float] = {}

        for source, weight in current.items():
            acc = source_acc.get(source)
            if acc is None or acc.total < 5:
                adjustments[source] = 0.0
                reasoning.append(f"{source}: insufficient data ({acc.total if acc else 0} trades)")
                continue

            # If this source wins >60%: increase weight
            # If this source wins <45%: decrease weight
            # Otherwise: no change
            delta = 0.0
            if acc.win_rate > 0.60:
                delta = WEIGHT_ADJUSTMENT_RATE
                reasoning.append(
                    f"{source}: {acc.win_rate:.0%} win rate → increase by {delta:.2f}"
                )
            elif acc.win_rate < 0.45:
                delta = -WEIGHT_ADJUSTMENT_RATE
                reasoning.append(
                    f"{source}: {acc.win_rate:.0%} win rate → decrease by {delta:.2f}"
                )
            else:
                reasoning.append(f"{source}: {acc.win_rate:.0%} win rate → keep")

            new_w = max(MIN_WEIGHT, min(MAX_WEIGHT, weight + delta))
            adjustments[source] = round(new_w - weight, 4)
            recommended[source] = new_w

        # Normalize recommended weights to sum to 1.0
        total_w = sum(recommended.values())
        if total_w > 0:
            recommended = {k: round(v / total_w, 4) for k, v in recommended.items()}

        # ── Compute threshold adjustment ────────────────────────────
        threshold_adj = 0
        if win_rate < 0.50:
            threshold_adj = THRESHOLD_ADJUSTMENT_UP
            reasoning.append(
                f"Win rate {win_rate:.0%} < 50% → raise threshold by {threshold_adj}"
            )
        elif win_rate > 0.65:
            threshold_adj = -THRESHOLD_ADJUSTMENT_DOWN
            reasoning.append(
                f"Win rate {win_rate:.0%} > 65% → lower threshold by {threshold_adj}"
            )
        else:
            reasoning.append(f"Win rate {win_rate:.0%} — threshold unchanged")

        return WeightAdjustment(
            current_weights=current,
            recommended_weights=recommended,
            adjustments=adjustments,
            source_accuracy={s: a.win_rate for s, a in source_acc.items()},
            total_trades=total,
            win_rate=win_rate,
            threshold_adjustment=threshold_adj,
            reasoning=reasoning,
        )

    def apply_adjustments(self, adjustment: WeightAdjustment) -> None:
        """Apply computed weight adjustments to current state.

        Only call this after reviewing the adjustment (or on a schedule).
        """
        with self._lock:
            self._current_weights = dict(adjustment.recommended_weights)
            new_delta = self._threshold_delta + adjustment.threshold_adjustment
            self._threshold_delta = max(
                THRESHOLD_FLOOR - 55,  # Don't go below floor
                min(THRESHOLD_CEILING - 55, new_delta),  # Don't exceed ceiling
            )
        logger.info(
            "Applied weight adjustments: weights=%s threshold_delta=%d",
            adjustment.recommended_weights,
            self._threshold_delta,
        )

    def reset(self) -> None:
        """Reset to base weights (for testing or manual override)."""
        with self._lock:
            self._current_weights = dict(self._base_weights)
            self._threshold_delta = 0
