"""EquityMeanReversion — US Equity Mean Reversion Strategy
========================================================
Below BB lower, RSI<30, volume spike. Exit: above SMA20. Stop: -4%
"""

import pandas as pd

from nautilus.strategies.base import NautilusStrategyBase


class EquityMeanReversion(NautilusStrategyBase):

    name = "EquityMeanReversion"
    stoploss = -0.04
    atr_multiplier = 1.5

    buy_rsi_threshold: int = 30
    sell_sma_period: int = 20
    volume_factor: float = 1.5

    def should_enter(self, ind: pd.Series) -> bool:
        # Price below lower Bollinger Band
        if ind.get("close", 0) >= ind.get("bb_lower", 0):
            return False

        # RSI oversold
        if ind.get("rsi_14", 50) >= self.buy_rsi_threshold:
            return False

        # Volume spike confirmation
        return bool(not ind.get("volume_ratio", 0) < self.volume_factor)

    def should_exit(self, ind: pd.Series) -> bool:
        # Price back above SMA20 (mean reversion complete)
        return bool(ind.get("close", 0) > ind.get(f"sma_{self.sell_sma_period}", 0))
