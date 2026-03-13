"""ForexRange — Forex Range Trading Strategy
===========================================
BB band touch + RSI divergence, ADX<20 (ranging).
Exit: midline. Stop: -1.5%
"""

import pandas as pd

from nautilus.strategies.base import NautilusStrategyBase


class ForexRange(NautilusStrategyBase):

    name = "ForexRange"
    stoploss = -0.015
    atr_multiplier = 1.0

    adx_ceiling: int = 20
    buy_rsi_threshold: int = 30
    sell_rsi_threshold: int = 70

    def should_enter(self, ind: pd.Series) -> bool:
        # ADX low = ranging market
        if ind.get("adx_14", 50) >= self.adx_ceiling:
            return False

        # Price near lower BB band
        close = ind.get("close", 0)
        bb_lower = ind.get("bb_lower", 0)
        bb_width = ind.get("bb_width", 0)
        if bb_lower <= 0 or bb_width <= 0:
            return False
        if close > bb_lower * 1.005:  # Within 0.5% of lower band
            return False

        # RSI oversold (divergence zone)
        return bool(not ind.get("rsi_14", 50) >= self.buy_rsi_threshold)

    def should_exit(self, ind: pd.Series) -> bool:
        # Price reaches midline (BB middle)
        if ind.get("close", 0) >= ind.get("bb_mid", 0):
            return True

        # RSI overbought
        return bool(ind.get("rsi_14", 50) > self.sell_rsi_threshold)
