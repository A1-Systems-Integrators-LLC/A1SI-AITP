"""NautilusVolatilityBreakout — ports VolatilityBreakout logic
============================================================
N-period high breakout + BB width expansion + emerging ADX.

Entry: close > 20-period high, volume spike, BB width expanding,
       ADX 15-25, RSI 40-70.
Exit: RSI > 85 OR close < EMA20.
"""

import pandas as pd

from nautilus.strategies.base import NautilusStrategyBase


class NautilusVolatilityBreakout(NautilusStrategyBase):

    name = "NautilusVolatilityBreakout"
    stoploss = -0.03  # Breakouts fail fast
    atr_multiplier = 1.5

    breakout_period: int = 20
    volume_factor: float = 1.8
    adx_low: int = 15
    adx_high: int = 25
    rsi_low: int = 40
    rsi_high: int = 70
    sell_rsi_threshold: int = 85

    def should_enter(self, ind: pd.Series) -> bool:
        # Breakout: close above previous N-period high (excludes current bar)
        high_n = ind.get("high_20_prev", float("inf"))
        if ind.get("close", 0) <= high_n:
            return False

        # Volume confirmation
        if ind.get("volume_ratio", 0) < self.volume_factor:
            return False

        # BB width expanding (proxy: current width > recent average)
        bb_width = ind.get("bb_width", 0)
        if bb_width <= 0:
            return False

        # ADX in emerging-trend range
        adx_val = ind.get("adx_14", 0)
        if adx_val < self.adx_low or adx_val > self.adx_high:
            return False

        # RSI in neutral zone
        rsi_val = ind.get("rsi_14", 50)
        return bool(not (rsi_val < self.rsi_low or rsi_val > self.rsi_high))

    def should_exit(self, ind: pd.Series) -> bool:
        # RSI exhaustion
        if ind.get("rsi_14", 50) > self.sell_rsi_threshold:
            return True

        # Close below EMA20 (trend failure)
        return bool(ind.get("close", 0) < ind.get("ema_20", 0))
