"""NautilusMeanReversion — ports BollingerMeanReversion logic
===========================================================
Bollinger Band lower touch + RSI oversold + low ADX (ranging market).

Entry: close < BB lower, RSI < 35, volume spike > 1.5x, ADX < 30.
Exit: close > BB mid OR RSI > 65.
"""

import pandas as pd

from nautilus.strategies.base import NautilusStrategyBase


class NautilusMeanReversion(NautilusStrategyBase):

    name = "NautilusMeanReversion"
    stoploss = -0.04
    atr_multiplier = 1.5

    buy_rsi_threshold: int = 35
    sell_rsi_threshold: int = 65
    volume_factor: float = 1.5
    adx_ceiling: int = 30

    def should_enter(self, ind: pd.Series) -> bool:
        # Price below lower Bollinger Band
        if ind.get("close", 0) >= ind.get("bb_lower", 0):
            return False

        # RSI oversold (but not extreme)
        rsi_val = ind.get("rsi_14", 50)
        if rsi_val >= self.buy_rsi_threshold or rsi_val < 10:
            return False

        # Volume spike
        if ind.get("volume_ratio", 0) < self.volume_factor:
            return False

        # Ranging market (low ADX)
        return bool(not ind.get("adx_14", 50) >= self.adx_ceiling)

    def should_exit(self, ind: pd.Series) -> bool:
        # Price reaches middle band (mean reversion target)
        if ind.get("close", 0) > ind.get("bb_mid", float("inf")):
            return True

        # RSI shows strength
        return bool(ind.get("rsi_14", 50) > self.sell_rsi_threshold)
