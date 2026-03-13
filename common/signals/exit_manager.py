"""Conviction-aware exit management — regime-adaptive exits, partial profit taking, time limits."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from common.regime.regime_detector import Regime, RegimeState
from common.signals.asset_tuning import get_config
from common.signals.constants import (
    ALIGNMENT_TABLES,
    DEFAULT_MAX_HOLD_HOURS,
    MAX_HOLD_HOURS,
    PARTIAL_PROFIT_TARGETS,
    REGIME_DETERIORATION_THRESHOLD,
    STOP_TIGHTENING_MULTIPLIER,
    TIME_EXIT_REGIME_MULTIPLIER,
    URGENCY_IMMEDIATE,
    URGENCY_MONITOR,
    URGENCY_NEXT_CANDLE,
)

logger = logging.getLogger("exit_manager")


@dataclass
class ExitAdvice:
    """Recommendation from the exit manager."""

    should_exit: bool
    reason: str
    urgency: str  # "immediate" | "next_candle" | "monitor"
    partial_pct: float  # 0.0 = full exit, 0.5 = exit half, etc.


def advise_exit(
    *,
    symbol: str,
    strategy_name: str,
    asset_class: str,
    entry_regime: Regime,
    current_regime_state: RegimeState,
    entry_time: datetime,
    current_time: datetime | None = None,
    current_profit_pct: float,
    already_exited_pct: float = 0.0,
) -> ExitAdvice:
    """Determine whether a position should be exited and how.

    Checks (in priority order):
    1. Regime deterioration (profitable positions in worsened conditions)
    2. Partial profit taking (strategy-specific targets)
    3. Time-based exit (max hold hours × regime multiplier)

    Args:
        symbol: Trading pair/instrument.
        strategy_name: Name of the strategy that opened the position.
        asset_class: "crypto", "equity", or "forex".
        entry_regime: Regime at position entry.
        current_regime_state: Current regime state.
        entry_time: When the position was opened.
        current_time: Now (defaults to utcnow).
        current_profit_pct: Unrealised P&L as a decimal fraction (0.05 = +5%).
        already_exited_pct: Fraction already partially exited (0.0-1.0).

    Returns:
        ExitAdvice with recommendation.
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    current_regime = current_regime_state.regime

    # ── 1. Regime deterioration exit ─────────────────────────────────────
    advice = _check_regime_deterioration(
        strategy_name=strategy_name,
        asset_class=asset_class,
        entry_regime=entry_regime,
        current_regime=current_regime,
        current_profit_pct=current_profit_pct,
    )
    if advice is not None:
        logger.info(
            "Exit advice [regime deterioration] %s %s: %s",
            symbol,
            strategy_name,
            advice.reason,
        )
        return advice

    # ── 2. Partial profit taking ─────────────────────────────────────────
    advice = _check_partial_profit(
        strategy_name=strategy_name,
        current_profit_pct=current_profit_pct,
        already_exited_pct=already_exited_pct,
    )
    if advice is not None:
        logger.info(
            "Exit advice [partial profit] %s %s: %s",
            symbol,
            strategy_name,
            advice.reason,
        )
        return advice

    # ── 3. Time-based exit ───────────────────────────────────────────────
    advice = _check_time_exit(
        strategy_name=strategy_name,
        asset_class=asset_class,
        entry_time=entry_time,
        current_time=current_time,
        current_regime=current_regime,
    )
    if advice is not None:
        logger.info(
            "Exit advice [time limit] %s %s: %s",
            symbol,
            strategy_name,
            advice.reason,
        )
        return advice

    # ── No exit condition met ────────────────────────────────────────────
    return ExitAdvice(
        should_exit=False,
        reason="No exit conditions met",
        urgency=URGENCY_MONITOR,
        partial_pct=0.0,
    )


def get_stop_multiplier(current_regime: Regime) -> float:
    """Return the ATR-stop tightening multiplier for the current regime.

    Lower values = tighter stop (closer to entry price).
    """
    return STOP_TIGHTENING_MULTIPLIER.get(current_regime, 0.8)


# ── Private helpers ──────────────────────────────────────────────────────────


def _get_alignment_score(
    regime: Regime, strategy_name: str, asset_class: str
) -> float:
    """Look up alignment score from the matrix, defaulting to 50."""
    table = ALIGNMENT_TABLES.get(asset_class, ALIGNMENT_TABLES.get("crypto", {}))
    regime_row = table.get(regime, {})
    return float(regime_row.get(strategy_name, 50))


def _check_regime_deterioration(
    *,
    strategy_name: str,
    asset_class: str,
    entry_regime: Regime,
    current_regime: Regime,
    current_profit_pct: float,
) -> ExitAdvice | None:
    """Exit profitable positions if regime deteriorated against the strategy."""
    if entry_regime == current_regime:
        return None  # No change

    entry_alignment = _get_alignment_score(entry_regime, strategy_name, asset_class)
    current_alignment = _get_alignment_score(
        current_regime, strategy_name, asset_class
    )
    alignment_drop = entry_alignment - current_alignment

    if alignment_drop < REGIME_DETERIORATION_THRESHOLD:
        return None  # Not a significant deterioration

    # Only exit profitable positions on regime deterioration
    if current_profit_pct <= 0:
        return ExitAdvice(
            should_exit=False,
            reason=(
                f"Regime deteriorated ({entry_regime.value} → {current_regime.value}, "
                f"alignment drop {alignment_drop:.0f}) but position is at loss "
                f"({current_profit_pct:.1%}) — monitoring"
            ),
            urgency=URGENCY_MONITOR,
            partial_pct=0.0,
        )

    return ExitAdvice(
        should_exit=True,
        reason=(
            f"Regime deterioration: {entry_regime.value} → {current_regime.value} "
            f"(alignment drop {alignment_drop:.0f} >= {REGIME_DETERIORATION_THRESHOLD}), "
            f"profit {current_profit_pct:.1%}"
        ),
        urgency=URGENCY_IMMEDIATE,
        partial_pct=0.0,  # Full exit
    )


def _check_partial_profit(
    *,
    strategy_name: str,
    current_profit_pct: float,
    already_exited_pct: float,
) -> ExitAdvice | None:
    """Check if any partial profit target has been reached."""
    targets = PARTIAL_PROFIT_TARGETS.get(strategy_name)
    if not targets:
        return None

    # Iterate targets in reverse (highest first) to exit at best available tier
    for profit_threshold, close_fraction, label in reversed(targets):
        if current_profit_pct >= profit_threshold and already_exited_pct < close_fraction:
            return ExitAdvice(
                should_exit=True,
                reason=(
                    f"Partial profit target: {label} "
                    f"(profit {current_profit_pct:.1%} >= {profit_threshold:.0%}, "
                    f"closing {close_fraction:.0%} of position)"
                ),
                urgency=URGENCY_NEXT_CANDLE,
                partial_pct=close_fraction,
            )

    return None


def _check_time_exit(
    *,
    strategy_name: str,
    asset_class: str = "crypto",
    entry_time: datetime,
    current_time: datetime,
    current_regime: Regime,
) -> ExitAdvice | None:
    """Exit if position has exceeded max hold time (adjusted by regime and asset class)."""
    config = get_config(asset_class)
    base_hours = MAX_HOLD_HOURS.get(strategy_name, DEFAULT_MAX_HOLD_HOURS)
    asset_adjusted_hours = base_hours * config.max_hold_multiplier
    regime_multiplier = TIME_EXIT_REGIME_MULTIPLIER.get(current_regime, 0.8)
    max_hours = asset_adjusted_hours * regime_multiplier

    held_hours = (current_time - entry_time).total_seconds() / 3600.0

    if held_hours >= max_hours:
        return ExitAdvice(
            should_exit=True,
            reason=(
                f"Time limit: held {held_hours:.1f}h >= max {max_hours:.1f}h "
                f"({strategy_name} base {base_hours:.0f}h × "
                f"{regime_multiplier:.1f} regime multiplier)"
            ),
            urgency=URGENCY_NEXT_CANDLE,
            partial_pct=0.0,  # Full exit on time limit
        )

    return None
