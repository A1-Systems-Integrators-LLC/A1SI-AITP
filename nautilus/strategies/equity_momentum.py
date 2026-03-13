"""EquityMomentum — US Equity Momentum Strategy
==============================================
Price > SMA200, RSI pullback 30-50, MACD positive, volume spike.
Exit: RSI>75 or close < SMA50.
Stop: -3%
"""

import pandas as pd

from nautilus.strategies.base import NautilusStrategyBase


class EquityMomentum(NautilusStrategyBase):

    name = "EquityMomentum"
    stoploss = -0.03
    atr_multiplier = 2.0

    sma_slow: int = 200
    sma_fast: int = 50
    buy_rsi_low: int = 30
    buy_rsi_high: int = 50
    sell_rsi_threshold: int = 75

    def should_enter(self, ind: pd.Series) -> bool:
        # Price above SMA200 (long-term uptrend)
        if ind.get("close", 0) <= ind.get(f"sma_{self.sma_slow}", 0):
            return False

        # RSI pullback zone (30-50)
        rsi_val = ind.get("rsi_14", 50)
        if rsi_val < self.buy_rsi_low or rsi_val > self.buy_rsi_high:
            return False

        # MACD positive
        if ind.get("macd_hist", 0) <= 0:
            return False

        # Volume spike (above average)
        return bool(not ind.get("volume_ratio", 0) < 1.2)

    def should_exit(self, ind: pd.Series) -> bool:
        # RSI overbought
        if ind.get("rsi_14", 50) > self.sell_rsi_threshold:
            return True

        # Price below SMA50 (trend weakening)
        return bool(ind.get("close", 0) < ind.get(f"sma_{self.sma_fast}", 0))
