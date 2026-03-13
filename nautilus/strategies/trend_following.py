"""NautilusTrendFollowing — ports CryptoInvestorV1 logic
======================================================
EMA alignment + RSI pullback + MACD confirmation.

Entry: price > EMA21 > EMA100, RSI < 45, volume above average, MACD histogram positive or turning.
Exit: RSI > 80 OR price closes below EMA50.
"""

import pandas as pd

from nautilus.strategies.base import NautilusStrategyBase


class NautilusTrendFollowing(NautilusStrategyBase):
    name = "NautilusTrendFollowing"
    stoploss = -0.05
    atr_multiplier = 2.0

    # Relaxed to match CryptoInvestorV1 sprint P15 params
    ema_fast: int = 21
    ema_slow: int = 100
    buy_rsi_threshold: int = 45
    sell_rsi_threshold: int = 80

    def should_enter(self, ind: pd.Series) -> bool:
        # EMA alignment: price > fast EMA > slow EMA
        if ind.get(f"ema_{self.ema_fast}", 0) <= ind.get(f"ema_{self.ema_slow}", 0):
            return False
        if ind.get("close", 0) <= ind.get(f"ema_{self.ema_fast}", 0):
            return False

        # RSI pullback in uptrend
        if ind.get("rsi_14", 50) >= self.buy_rsi_threshold:
            return False

        # Volume confirmation
        if ind.get("volume_ratio", 0) < 0.8:
            return False

        # MACD momentum (histogram positive or turning positive)
        macd_hist = ind.get("macd_hist", 0)
        macd_hist_prev = ind.get("macd_hist_prev", 0)
        if macd_hist <= 0 and macd_hist <= macd_hist_prev:
            return False

        # Not near BB upper band (avoid chasing)
        return bool(not ind.get("close", 0) >= ind.get("bb_upper", float("inf")) * 0.98)

    def should_exit(self, ind: pd.Series) -> bool:
        # RSI overbought
        if ind.get("rsi_14", 50) > self.sell_rsi_threshold:
            return True

        # Price closed below fast EMA (trend weakening)
        return bool(ind.get("close", 0) < ind.get(f"ema_{self.ema_fast}", 0))
