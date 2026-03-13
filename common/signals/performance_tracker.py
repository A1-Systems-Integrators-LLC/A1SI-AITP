"""Signal performance tracking — records signal attributions and computes accuracy.

Provides the data layer for the adaptive feedback loop. Each trade entry
records which signal sources contributed and their scores; on trade exit
the outcome is backfilled so per-source accuracy can be computed.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("signal_performance_tracker")


@dataclass
class AttributionRecord:
    """Snapshot of signal components at time of trade entry."""

    order_id: str
    symbol: str
    asset_class: str
    strategy: str
    composite_score: float
    contributions: dict[str, float] = field(default_factory=dict)
    position_modifier: float = 1.0
    entry_regime: str = ""
    outcome: str = "open"  # win / loss / open
    pnl: float | None = None
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None


@dataclass
class SourceAccuracy:
    """Accuracy metrics for a single signal source."""

    source: str
    total: int = 0
    wins: int = 0
    losses: int = 0
    avg_score_win: float = 0.0
    avg_score_loss: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.total if self.total > 0 else 0.0

    @property
    def accuracy(self) -> float:
        """How predictive is this source? Higher score trades should win more."""
        if self.total < 5:
            return 0.5  # Not enough data
        return self.win_rate


class PerformanceTracker:
    """Tracks signal attribution records and computes per-source accuracy.

    Thread-safe via threading.Lock (consistent with RiskManager pattern).
    This is the in-memory tracker; the Django model provides persistence.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, AttributionRecord] = {}  # order_id -> record

    def record_entry(
        self,
        order_id: str,
        symbol: str,
        asset_class: str,
        strategy: str,
        composite_score: float,
        contributions: dict[str, float],
        position_modifier: float = 1.0,
        entry_regime: str = "",
    ) -> AttributionRecord:
        """Record signal components at trade entry time."""
        rec = AttributionRecord(
            order_id=order_id,
            symbol=symbol,
            asset_class=asset_class,
            strategy=strategy,
            composite_score=composite_score,
            contributions=dict(contributions),
            position_modifier=position_modifier,
            entry_regime=entry_regime,
        )
        with self._lock:
            self._records[order_id] = rec
        logger.info(
            "Signal recorded: %s %s %s score=%.1f",
            order_id[:8], symbol, strategy, composite_score,
        )
        return rec

    def record_outcome(
        self,
        order_id: str,
        outcome: str,
        pnl: float | None = None,
    ) -> AttributionRecord | None:
        """Backfill outcome for a previously recorded entry.

        Args:
            order_id: The order that was recorded at entry.
            outcome: "win" or "loss".
            pnl: Realized P&L for this trade.

        Returns:
            Updated record, or None if order_id not found.
        """
        with self._lock:
            rec = self._records.get(order_id)
            if rec is None:
                return None
            rec.outcome = outcome
            rec.pnl = pnl
            rec.resolved_at = datetime.now(timezone.utc)
        logger.info(
            "Outcome recorded: %s %s pnl=%s",
            order_id[:8], outcome, pnl,
        )
        return rec

    def get_source_accuracy(
        self,
        asset_class: str | None = None,
        strategy: str | None = None,
        window_days: int = 30,
    ) -> dict[str, SourceAccuracy]:
        """Compute per-source accuracy from resolved records.

        Args:
            asset_class: Filter by asset class (None = all).
            strategy: Filter by strategy (None = all).
            window_days: Only consider records within this many days.

        Returns:
            Dict mapping source name to SourceAccuracy.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - window_days * 86400
        source_wins: dict[str, list[float]] = defaultdict(list)
        source_losses: dict[str, list[float]] = defaultdict(list)

        with self._lock:
            for rec in self._records.values():
                if rec.outcome == "open":
                    continue
                if rec.recorded_at.timestamp() < cutoff:
                    continue
                if asset_class and rec.asset_class != asset_class:
                    continue
                if strategy and rec.strategy != strategy:
                    continue

                for source, score in rec.contributions.items():
                    if rec.outcome == "win":
                        source_wins[source].append(score)
                    else:
                        source_losses[source].append(score)

        all_sources = set(source_wins.keys()) | set(source_losses.keys())
        result: dict[str, SourceAccuracy] = {}

        for src in all_sources:
            wins = source_wins.get(src, [])
            losses = source_losses.get(src, [])
            acc = SourceAccuracy(
                source=src,
                total=len(wins) + len(losses),
                wins=len(wins),
                losses=len(losses),
                avg_score_win=sum(wins) / len(wins) if wins else 0.0,
                avg_score_loss=sum(losses) / len(losses) if losses else 0.0,
            )
            result[src] = acc

        return result

    def get_records(
        self,
        outcome: str | None = None,
        asset_class: str | None = None,
        limit: int = 100,
    ) -> list[AttributionRecord]:
        """Return recent attribution records, optionally filtered."""
        with self._lock:
            recs = list(self._records.values())

        if outcome:
            recs = [r for r in recs if r.outcome == outcome]
        if asset_class:
            recs = [r for r in recs if r.asset_class == asset_class]

        recs.sort(key=lambda r: r.recorded_at, reverse=True)
        return recs[:limit]

    def clear(self) -> None:
        """Clear all in-memory records (for testing)."""
        with self._lock:
            self._records.clear()
