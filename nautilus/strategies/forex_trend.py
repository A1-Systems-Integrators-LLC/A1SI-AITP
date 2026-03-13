"""ForexTrend — Forex Trend Following Strategy
=============================================
EMA 20/50 crossover, ADX>25, RSI confirm.
Exit: opposite crossover. Stop: -2%
"""

import pandas as pd

from nautilus.strategies.base import NautilusStrategyBase


class ForexTrend(NautilusStrategyBase):

    name = "ForexTrend"
    stoploss = -0.02
    atr_multiplier = 1.5

    ema_fast: int = 20
    ema_slow: int = 50
    adx_threshold: int = 25
    buy_rsi_low: int = 40
    buy_rsi_high: int = 70

    def should_enter(self, ind: pd.Series) -> bool:
        # EMA crossover: fast > slow
        if ind.get(f"ema_{self.ema_fast}", 0) <= ind.get(f"ema_{self.ema_slow}", 0):
            return False

        # ADX confirms trend strength
        if ind.get("adx_14", 0) < self.adx_threshold:
            return False

        # RSI not overbought
        rsi_val = ind.get("rsi_14", 50)
        return bool(not (rsi_val < self.buy_rsi_low or rsi_val > self.buy_rsi_high))

    def should_exit(self, ind: pd.Series) -> bool:
        # Opposite crossover: fast < slow
        return bool(ind.get(f"ema_{self.ema_fast}", 0) < ind.get(f"ema_{self.ema_slow}", 0))
