"""Shared conviction system integration for Freqtrade strategies.

Provides:
- Signal fetching from the entry-check API
- Conviction gate (approve/reject trades based on composite score)
- Position size scaling via position_modifier
- Exit advice via common.signals.exit_manager (direct import, optional)
- Regime-aware stop loss tightening (direct import, optional)
- Regime caching for entry/exit tracking

All external calls are fail-open: if the API or conviction modules are
unreachable, trades proceed as normal.
"""

import logging
import os
import sys
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── Ensure PROJECT_ROOT is on sys.path for common/ imports ──
_project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ── Try to import conviction system modules ──
try:
    from common.regime.regime_detector import (  # noqa: F401
        Regime,
        RegimeDetector,
        RegimeState,
    )
    from common.signals.exit_manager import advise_exit, get_stop_multiplier

    HAS_CONVICTION = True
except ImportError:
    HAS_CONVICTION = False
    logger.info("Conviction system not available (common.signals not on sys.path)")

# Signal cache refresh interval (seconds)
SIGNAL_REFRESH_INTERVAL = 300  # 5 minutes
# Maximum age of a cached signal before it's considered stale (seconds)
SIGNAL_MAX_AGE = 900  # 15 minutes


def fetch_signal(
    api_url: str, pair: str, strategy_name: str, side: str = "long",
) -> dict[str, Any] | None:
    """Fetch composite signal from entry-check API.

    Returns the API response dict or None on failure.
    """
    try:
        import requests

        symbol_url = pair.replace("/", "-")
        resp = requests.post(
            f"{api_url}/api/signals/{symbol_url}/entry-check/",
            json={"strategy": strategy_name, "asset_class": "crypto", "side": side},
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"Signal API returned {resp.status_code} for {pair}")
    except Exception as e:
        logger.warning(f"Signal fetch failed for {pair}: {e}")
    return None


def refresh_signals(strategy: Any) -> None:
    """Refresh cached signals for all active pairs.

    Called from bot_loop_start(). Throttled to every 5 minutes.
    Skipped in BACKTEST/HYPEROPT mode.
    """
    from freqtrade.enums import RunMode

    if strategy.dp and strategy.dp.runmode in (RunMode.BACKTEST, RunMode.HYPEROPT):
        return

    now = time.monotonic()
    last_fetch = getattr(strategy, "_last_signal_fetch", 0)
    if now - last_fetch < SIGNAL_REFRESH_INTERVAL:
        return

    if not hasattr(strategy, "_signals"):
        strategy._signals = {}

    pairs = strategy.dp.current_whitelist()
    strategy_name = strategy.__class__.__name__

    for pair in pairs:
        signal = fetch_signal(strategy.risk_api_url, pair, strategy_name)
        if signal:
            signal["_fetched_at"] = time.monotonic()
            strategy._signals[pair] = signal

    # Cache current regime state per pair for exit tracking
    if HAS_CONVICTION:
        if not hasattr(strategy, "_current_regimes"):
            strategy._current_regimes = {}
        for pair in pairs:
            try:
                dataframe, _ = strategy.dp.get_analyzed_dataframe(pair, strategy.timeframe)
                if not dataframe.empty:
                    detector = RegimeDetector()
                    state = detector.detect(dataframe)
                    strategy._current_regimes[pair] = state
            except Exception as e:
                logger.warning(f"Regime detect failed for {pair}: {e}")

    strategy._last_signal_fetch = now
    logger.info(f"Refreshed conviction signals for {len(strategy._signals)} pairs")


def check_strategy_paused(strategy: Any) -> bool:
    """Check if the strategy is paused by the orchestrator.

    Queries the strategy-status API. Fail-open: returns False (not paused)
    if API unreachable.
    """
    from freqtrade.enums import RunMode

    if strategy.dp and strategy.dp.runmode in (RunMode.BACKTEST, RunMode.HYPEROPT):
        return False

    strategy_name = strategy.__class__.__name__
    now = time.monotonic()

    # Cache pause status for 60 seconds
    cache = getattr(strategy, "_pause_cache", {})
    cached = cache.get(strategy_name)
    if cached and (now - cached["ts"]) < 60:
        return cached["paused"]

    try:
        import requests

        resp = requests.get(
            f"{strategy.risk_api_url}/api/signals/strategy-status/",
            params={"asset_class": "crypto"},
            timeout=5,
        )
        if resp.status_code == 200:
            for entry in resp.json():
                if entry.get("strategy_name") == strategy_name:
                    paused = entry.get("recommended_action") == "pause"
                    if not hasattr(strategy, "_pause_cache"):
                        strategy._pause_cache = {}
                    strategy._pause_cache[strategy_name] = {"paused": paused, "ts": now}
                    if paused:
                        logger.warning(
                            f"Strategy {strategy_name} PAUSED by orchestrator "
                            f"(regime={entry.get('regime')}, "
                            f"alignment={entry.get('alignment_score')})",
                        )
                    return paused
    except Exception as e:
        logger.warning(f"Strategy pause check failed: {e}")

    return False  # fail-open


def check_conviction(strategy: Any, pair: str) -> bool:
    """Check conviction gate. Returns True if trade should proceed.

    Checks orchestrator pause status first, then conviction signal.
    Fail-open: returns True if signal unavailable.
    """
    # Check orchestrator pause first
    if check_strategy_paused(strategy):
        return False

    signal = getattr(strategy, "_signals", {}).get(pair)

    # Check if cached signal is stale
    if signal is not None and "_fetched_at" in signal:
        fetched_at = signal["_fetched_at"]
        if time.monotonic() - fetched_at > SIGNAL_MAX_AGE:
            logger.warning(f"Stale conviction signal for {pair} (>{SIGNAL_MAX_AGE}s), refreshing")
            signal = None

    # Try fresh fetch if not cached or stale
    if signal is None:
        signal = fetch_signal(
            strategy.risk_api_url, pair, strategy.__class__.__name__,
        )
        if signal:
            signal["_fetched_at"] = time.monotonic()
            if not hasattr(strategy, "_signals"):
                strategy._signals = {}
            strategy._signals[pair] = signal

    if signal is None:
        logger.warning(f"No conviction signal for {pair}, approving (fail-open)")
        return True

    if not signal.get("approved", True):
        logger.warning(
            f"Conviction gate REJECTED {pair}: "
            f"score={signal.get('score', 0):.1f}, "
            f"label={signal.get('signal_label', 'unknown')}",
        )
        return False

    logger.info(
        f"Conviction gate approved {pair}: "
        f"score={signal.get('score', 0):.1f}, "
        f"label={signal.get('signal_label', 'unknown')}",
    )
    return True


def record_entry_regime(strategy: Any, pair: str) -> None:
    """Record the current regime at trade entry time for exit tracking."""
    if not HAS_CONVICTION:
        return
    if not hasattr(strategy, "_entry_regimes"):
        strategy._entry_regimes = {}

    regime_state = getattr(strategy, "_current_regimes", {}).get(pair)
    if regime_state:
        strategy._entry_regimes[pair] = regime_state.regime.value
    else:
        # Try to detect now
        try:
            dataframe, _ = strategy.dp.get_analyzed_dataframe(pair, strategy.timeframe)
            if not dataframe.empty:
                detector = RegimeDetector()
                state = detector.detect(dataframe)
                strategy._entry_regimes[pair] = state.regime.value
        except Exception as e:
            logger.warning(f"Could not record entry regime for {pair}: {e}")


def get_position_modifier(strategy: Any, pair: str) -> float:
    """Get position size modifier from cached signal.

    Returns 1.0 (full size) if no signal available.
    Multiplied by profit reinvestment stake multiplier when available.
    """
    modifier = 1.0
    signal = getattr(strategy, "_signals", {}).get(pair)
    if signal:
        modifier = signal.get("position_modifier", 1.0)

    # Scale by profit reinvestment tracker
    try:
        from common.risk.profit_tracker import ProfitTracker

        tracker = ProfitTracker.get_instance()
        modifier *= tracker.get_stake_multiplier()
    except Exception:
        pass  # fail-open

    return modifier


def check_exit_advice(
    strategy: Any,
    pair: str,
    trade: Any,
    current_time: datetime,
    current_profit: float,
) -> str | None:
    """Check conviction-based exit conditions.

    Returns exit tag string or None.
    Requires HAS_CONVICTION=True (common.signals importable).
    """
    if not HAS_CONVICTION:
        return None

    entry_regimes = getattr(strategy, "_entry_regimes", {})
    entry_regime_name = entry_regimes.get(pair)

    if not entry_regime_name:
        return None

    try:
        entry_regime = Regime(entry_regime_name)

        # Get current regime state (cached or detect fresh)
        current_state = getattr(strategy, "_current_regimes", {}).get(pair)
        if current_state is None:
            dataframe, _ = strategy.dp.get_analyzed_dataframe(pair, strategy.timeframe)
            if dataframe.empty:
                return None
            detector = RegimeDetector()
            current_state = detector.detect(dataframe)

        advice = advise_exit(
            symbol=pair,
            strategy_name=strategy.__class__.__name__,
            asset_class="crypto",
            entry_regime=entry_regime,
            current_regime_state=current_state,
            entry_time=trade.open_date_utc,
            current_time=current_time,
            current_profit_pct=current_profit * 100,
        )

        if advice.should_exit:
            tag = f"conviction_{advice.reason.replace(' ', '_')[:30]}"
            logger.info(
                f"Exit advisor: {pair} — {advice.reason} "
                f"(urgency={advice.urgency}, partial={advice.partial_pct})",
            )
            return tag
    except Exception as e:
        logger.warning(f"Exit advisor failed for {pair}: {e}")

    return None


def get_regime_stop_multiplier(strategy: Any, pair: str) -> float:
    """Get regime-aware stop loss multiplier (0.5-1.0).

    Lower values = tighter stops in unfavorable regimes.
    Returns 1.0 if conviction system unavailable.
    """
    if not HAS_CONVICTION:
        return 1.0

    regime_state = getattr(strategy, "_current_regimes", {}).get(pair)
    if regime_state:
        return get_stop_multiplier(regime_state.regime)

    # Try to detect fresh
    try:
        dataframe, _ = strategy.dp.get_analyzed_dataframe(pair, strategy.timeframe)
        if not dataframe.empty:
            detector = RegimeDetector()
            state = detector.detect(dataframe)
            return get_stop_multiplier(state.regime)
    except Exception as e:
        logger.warning(f"Regime stop multiplier failed for {pair}: {e}")

    return 1.0
