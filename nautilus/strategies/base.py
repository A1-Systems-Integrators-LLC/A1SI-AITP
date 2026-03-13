"""NautilusTrader Strategy Base Class
===================================
Shared functionality for all Nautilus strategies:
- Indicator computation via common.indicators.technical
- Risk API gating (same pattern as Freqtrade strategies)
- Conviction gating via entry-check API (IEB Phase 6)
- ATR-based position sizing with conviction modifier
- Conviction-aware exit advisor
- Bounded bar buffer for memory efficiency
"""

import logging
import time
from collections import deque
from datetime import datetime, timezone

import pandas as pd

from common.indicators.technical import (
    adx,
    atr_indicator,
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
)

logger = logging.getLogger(__name__)

# Maximum bars to keep in memory
MAX_BARS = 5000

# Risk API defaults (same as Freqtrade strategies)
RISK_API_URL = "http://127.0.0.1:8000"
RISK_PORTFOLIO_ID = 1

# Signal cache refresh interval (seconds)
SIGNAL_REFRESH_INTERVAL = 300  # 5 minutes

# Strategy name → asset class mapping
STRATEGY_ASSET_CLASS: dict[str, str] = {
    "NautilusTrendFollowing": "crypto",
    "NautilusMeanReversion": "crypto",
    "NautilusVolatilityBreakout": "crypto",
    "EquityMomentum": "equity",
    "EquityMeanReversion": "equity",
    "ForexTrend": "forex",
    "ForexRange": "forex",
}

# Try to import conviction system modules
try:
    from common.regime.regime_detector import Regime, RegimeDetector
    from common.signals.exit_manager import advise_exit, get_stop_multiplier

    HAS_CONVICTION = True
except ImportError:  # pragma: no cover
    HAS_CONVICTION = False


class NautilusStrategyBase:
    """Base class for NautilusTrader strategies.

    Provides indicator computation, risk gating, and position sizing
    that mirror the Freqtrade strategy patterns. Subclasses implement
    ``should_enter()`` and ``should_exit()`` with pandas-based logic.

    In backtest mode, the runner calls ``on_bar()`` for each bar. The
    strategy maintains a rolling window of OHLCV data and evaluates
    entry/exit signals on each bar.
    """

    name: str = "base"
    timeframe: str = "1h"
    stoploss: float = -0.05
    atr_multiplier: float = 2.0

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.bars: deque = deque(maxlen=self.config.get("max_bars", MAX_BARS))
        self.position: dict | None = None  # {side, entry_price, size, entry_time}
        self.trades: list[dict] = []
        self.fee_rate = self.config.get("fee_rate", 0.001)  # 0.1% per side (taker)
        self.risk_api_url = self.config.get("risk_api_url", RISK_API_URL)
        self.risk_portfolio_id = self.config.get("risk_portfolio_id", RISK_PORTFOLIO_ID)

        # Conviction system state
        self._signals: dict[str, dict] = {}
        self._last_signal_fetch: float = 0
        self._entry_regime: str | None = None  # regime name at entry time

    def on_bar(self, bar: dict) -> dict | None:
        """Process a single OHLCV bar. Returns a trade dict if a fill occurred."""
        self.bars.append(bar)

        # Need enough bars for indicator computation
        if len(self.bars) < 200:
            return None

        df = self._bars_to_df()
        indicators = self._compute_indicators(df)

        if self.position is None:
            if self.should_enter(indicators):
                entry_price = bar["close"]
                size = self._compute_position_size(indicators, entry_price)
                if size > 0 and self._check_risk_gate(bar, entry_price, size):
                    # Conviction gate (skip in backtest mode)
                    if not self._check_conviction_gate():
                        return None

                    # Apply position modifier from conviction signal
                    modifier = self._get_position_modifier()
                    size = round(size * modifier, 6)
                    if size <= 0:
                        return None

                    self.position = {
                        "side": "long",
                        "entry_price": entry_price,
                        "size": size,
                        "entry_time": bar["timestamp"],
                    }
                    # Record entry regime for exit advisor
                    self._record_entry_regime(df)
        else:
            # Check conviction-based exit advisor
            exit_tag = self._check_exit_advice(bar)
            if exit_tag:
                return self._make_trade(bar["close"], bar)

            if self.should_exit(indicators):
                return self._make_trade(bar["close"], bar)

            # Check stop loss (regime-aware tightening)
            current_price = bar["close"]
            effective_stoploss = self.stoploss * self._get_stop_multiplier()
            loss_pct = (current_price / self.position["entry_price"]) - 1
            if loss_pct <= effective_stoploss:
                return self._make_trade(current_price, bar)

        return None

    def on_stop(self) -> dict | None:
        """Flatten any open position at the last bar's close."""
        if self.position is not None and len(self.bars) > 0:
            last_bar = self.bars[-1]
            return self._make_trade(last_bar["close"], last_bar)
        return None

    def _make_trade(self, exit_price: float, bar: dict) -> dict:
        """Build a trade dict with fee deduction."""
        entry_price = self.position["entry_price"]
        size = self.position["size"]
        fee = (entry_price + exit_price) * size * self.fee_rate
        raw_pnl = (exit_price - entry_price) * size
        pnl = raw_pnl - fee
        pnl_pct = (exit_price / entry_price) - 1 - (2 * self.fee_rate)
        trade = {
            "entry_time": self.position["entry_time"],
            "exit_time": bar["timestamp"],
            "side": self.position["side"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "size": size,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "fee": fee,
        }
        self.trades.append(trade)
        self.position = None
        return trade

    def should_enter(self, indicators: pd.Series) -> bool:
        """Override in subclass: return True to enter a long position."""
        raise NotImplementedError

    def should_exit(self, indicators: pd.Series) -> bool:
        """Override in subclass: return True to exit the current position."""
        raise NotImplementedError

    def _bars_to_df(self) -> pd.DataFrame:
        """Convert bar buffer to a pandas DataFrame."""
        df = pd.DataFrame(list(self.bars))
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.set_index("timestamp")
        return df

    def _compute_indicators(self, df: pd.DataFrame) -> pd.Series:
        """Compute standard indicators and return the last row as a Series."""
        result = df.copy()

        # EMAs
        for p in [7, 14, 20, 21, 50, 100, 200]:
            result[f"ema_{p}"] = ema(result["close"], p)
            result[f"sma_{p}"] = sma(result["close"], p)

        # RSI
        result["rsi_14"] = rsi(result["close"], 14)

        # MACD
        macd_df = macd(result["close"])
        result["macd"] = macd_df["macd"]
        result["macd_signal"] = macd_df["macd_signal"]
        result["macd_hist"] = macd_df["macd_hist"]
        result["macd_hist_prev"] = macd_df["macd_hist"].shift(1)

        # Bollinger Bands
        bb = bollinger_bands(result["close"], 20, 2.0)
        result["bb_upper"] = bb["bb_upper"]
        result["bb_mid"] = bb["bb_mid"]
        result["bb_lower"] = bb["bb_lower"]
        result["bb_width"] = bb["bb_width"]

        # ATR
        result["atr_14"] = atr_indicator(result, 14)

        # ADX
        result["adx_14"] = adx(result, 14)

        # Volume
        result["volume_sma_20"] = sma(result["volume"], 20)
        result["volume_ratio"] = result["volume"] / result["volume_sma_20"]

        # N-period highs (for breakout)
        result["high_20"] = result["high"].rolling(window=20).max()
        # Shifted variant excludes current bar (proper breakout detection)
        result["high_20_prev"] = result["high"].shift(1).rolling(window=20).max()

        return result.iloc[-1]

    def _compute_position_size(self, indicators: pd.Series, entry_price: float) -> float:
        """ATR-based position sizing. Returns size in base currency units."""
        atr = indicators.get("atr_14", 0)
        if atr <= 0 or entry_price <= 0:
            return 0.0

        # Risk per trade: 2% of notional per ATR unit
        risk_per_unit = atr * abs(self.atr_multiplier)
        if risk_per_unit <= 0:
            return 0.0

        initial_balance = self.config.get("initial_balance", 10000.0)
        risk_amount = initial_balance * 0.02  # 2% risk
        size = risk_amount / risk_per_unit
        return round(size, 6)

    def _check_risk_gate(self, bar: dict, entry_price: float, size: float) -> bool:
        """Call the backend risk API to approve the trade. Skip in backtest mode."""
        if self.config.get("mode") == "backtest":
            return True

        try:
            import requests

            stop_loss_price = entry_price * (1 + self.stoploss)
            resp = requests.post(
                f"{self.risk_api_url}/api/risk/{self.risk_portfolio_id}/check-trade/",
                json={
                    "symbol": self.config.get("symbol", "BTC/USDT"),
                    "side": "long",
                    "size": size,
                    "entry_price": entry_price,
                    "stop_loss_price": stop_loss_price,
                },
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("approved", False):
                    logger.warning(f"Risk gate REJECTED: {data.get('reason')}")
                    return False
                return True
            logger.warning(f"Risk API returned {resp.status_code}, rejecting trade")
            return False
        except Exception as e:
            logger.error(f"Risk API unreachable ({e}), rejecting trade")
            return False

    # ── Conviction System Integration ──────────────────────────

    def _get_asset_class(self) -> str:
        """Return the asset class for this strategy."""
        return STRATEGY_ASSET_CLASS.get(self.name, "crypto")

    def _fetch_signal(self) -> dict | None:
        """Fetch composite signal from entry-check API."""
        try:
            import requests

            symbol = self.config.get("symbol", "BTC/USDT")
            symbol_url = symbol.replace("/", "-")
            resp = requests.post(
                f"{self.risk_api_url}/api/signals/{symbol_url}/entry-check/",
                json={
                    "strategy": self.name,
                    "asset_class": self._get_asset_class(),
                },
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Signal API returned {resp.status_code} for {symbol}")
        except Exception as e:
            logger.warning(f"Signal fetch failed: {e}")
        return None

    def _refresh_signal(self) -> None:
        """Refresh cached signal if stale. Throttled to SIGNAL_REFRESH_INTERVAL."""
        now = time.monotonic()
        if now - self._last_signal_fetch < SIGNAL_REFRESH_INTERVAL:
            return

        signal = self._fetch_signal()
        if signal:
            symbol = self.config.get("symbol", "BTC/USDT")
            self._signals[symbol] = signal
        self._last_signal_fetch = now

    def _get_cached_signal(self) -> dict | None:
        """Get the cached signal for the current symbol."""
        symbol = self.config.get("symbol", "BTC/USDT")
        return self._signals.get(symbol)

    def _check_conviction_gate(self) -> bool:
        """Check conviction gate. Returns True if trade should proceed.

        Skips in backtest mode. Fail-open: returns True if signal unavailable.
        """
        if self.config.get("mode") == "backtest":
            return True

        self._refresh_signal()
        signal = self._get_cached_signal()

        # Try fresh fetch if not cached
        if signal is None:
            signal = self._fetch_signal()
            if signal:
                symbol = self.config.get("symbol", "BTC/USDT")
                self._signals[symbol] = signal

        if signal is None:
            logger.warning("No conviction signal, approving (fail-open)")
            return True

        if not signal.get("approved", True):
            logger.warning(
                f"Conviction gate REJECTED: "
                f"score={signal.get('score', 0):.1f}, "
                f"label={signal.get('signal_label', 'unknown')}",
            )
            return False

        logger.info(
            f"Conviction gate approved: "
            f"score={signal.get('score', 0):.1f}, "
            f"label={signal.get('signal_label', 'unknown')}",
        )
        return True

    def _get_position_modifier(self) -> float:
        """Get position size modifier from cached signal. Returns 1.0 if unavailable."""
        if self.config.get("mode") == "backtest":
            return 1.0
        signal = self._get_cached_signal()
        if signal:
            return signal.get("position_modifier", 1.0)
        return 1.0

    def _record_entry_regime(self, df: pd.DataFrame) -> None:
        """Record the current regime at trade entry for exit advisor."""
        if not HAS_CONVICTION:
            return
        try:
            detector = RegimeDetector()
            state = detector.detect(df)
            self._entry_regime = state.regime.value
        except Exception as e:
            logger.warning(f"Could not record entry regime: {e}")

    def _check_exit_advice(self, bar: dict) -> str | None:
        """Check conviction-based exit conditions. Returns exit tag or None.

        Skips in backtest mode or when conviction system unavailable.
        """
        if self.config.get("mode") == "backtest":
            return None
        if not HAS_CONVICTION:
            return None
        if self.position is None or self._entry_regime is None:
            return None

        try:
            entry_regime = Regime(self._entry_regime)
            df = self._bars_to_df()
            detector = RegimeDetector()
            current_state = detector.detect(df)

            entry_price = self.position["entry_price"]
            current_price = bar["close"]
            current_profit_pct = ((current_price / entry_price) - 1) * 100

            entry_time = self.position["entry_time"]
            if isinstance(entry_time, pd.Timestamp):
                current_time = pd.Timestamp(bar["timestamp"])
            else:
                current_time = datetime.now(timezone.utc)

            advice = advise_exit(
                symbol=self.config.get("symbol", "BTC/USDT"),
                strategy_name=self.name,
                asset_class=self._get_asset_class(),
                entry_regime=entry_regime,
                current_regime_state=current_state,
                entry_time=entry_time,
                current_time=current_time,
                current_profit_pct=current_profit_pct,
            )

            if advice.should_exit:
                tag = f"conviction_{advice.reason.replace(' ', '_')[:30]}"
                logger.info(
                    f"Exit advisor: {advice.reason} "
                    f"(urgency={advice.urgency}, partial={advice.partial_pct})",
                )
                return tag
        except Exception as e:
            logger.warning(f"Exit advisor failed: {e}")

        return None

    def _get_stop_multiplier(self) -> float:
        """Get regime-aware stop loss multiplier (0.5-1.0).

        Lower values = tighter stops in unfavorable regimes.
        Returns 1.0 in backtest mode or when conviction system unavailable.
        """
        if self.config.get("mode") == "backtest":
            return 1.0
        if not HAS_CONVICTION:
            return 1.0

        try:
            df = self._bars_to_df()
            detector = RegimeDetector()
            state = detector.detect(df)
            return get_stop_multiplier(state.regime)
        except Exception as e:
            logger.warning(f"Regime stop multiplier failed: {e}")
            return 1.0

    def get_trades_df(self) -> pd.DataFrame:
        """Return all closed trades as a DataFrame."""
        if not self.trades:
            return pd.DataFrame()
        df = pd.DataFrame(self.trades)
        for col in ["entry_time", "exit_time"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], utc=True)
        return df
