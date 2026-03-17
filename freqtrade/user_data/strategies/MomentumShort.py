"""MomentumShort — Dedicated short-only strategy.

Targets overbought conditions with bearish momentum confirmation.
EMA bearish alignment + RSI overbought + MACD cross down + volume.
Tight stops (-6%), fast ROI targets.
"""

import logging

import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

logger = logging.getLogger(__name__)

# Conviction helpers (fail-open)
try:
    from freqtrade.user_data.strategies._conviction_helpers import (
        check_conviction,
        check_exit_advice,
        get_position_modifier,
        get_regime_stop_multiplier,
        record_entry_regime,
        refresh_signals,
    )

    HAS_CONVICTION = True
except ImportError:
    HAS_CONVICTION = False


class MomentumShort(IStrategy):
    """Short-only momentum strategy targeting overbought reversals."""

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    startup_candle_count = 100

    stoploss = -0.06
    use_custom_stoploss = True

    minimal_roi = {
        "0": 0.04,
        "60": 0.025,
        "180": 0.015,
    }

    # Hyperopt parameters
    sell_ema_fast = IntParameter(10, 30, default=14, space="sell")
    sell_ema_slow = IntParameter(40, 120, default=50, space="sell")
    sell_rsi_threshold = IntParameter(60, 80, default=65, space="sell")
    sell_volume_factor = DecimalParameter(0.5, 3.0, default=1.2, space="sell")
    atr_multiplier = DecimalParameter(1.0, 3.0, default=2.0, space="sell")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.sell_ema_fast.value)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.sell_ema_slow.value)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]
        dataframe["macd_hist"] = macd["macdhist"]
        dataframe["macd_hist_prev"] = dataframe["macd_hist"].shift(1)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["volume_sma"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_sma"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # No long entries — short-only strategy
        dataframe.loc[:, "enter_long"] = 0

        # Short entries: bearish momentum
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["rsi"] > self.sell_rsi_threshold.value)
                & (dataframe["macd_hist"] < dataframe["macd_hist_prev"])
                & (dataframe["volume_ratio"] > self.sell_volume_factor.value)
                & (dataframe["volume"] > 0)
                & (dataframe["rsi"] < 90)
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "exit_long"] = 0

        # Exit short: RSI oversold or MACD turning bullish
        dataframe.loc[
            (
                (dataframe["rsi"] < 35)
                | (
                    (dataframe["macd_hist"] > dataframe["macd_hist_prev"])
                    & (dataframe["rsi"] < 50)
                )
            ),
            "exit_short",
        ] = 1

        return dataframe

    def custom_leverage(self, pair: str, current_time, current_rate, proposed_leverage,
                        max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3.0, max_leverage)

    def bot_loop_start(self, **kwargs) -> None:
        if HAS_CONVICTION:
            refresh_signals(self)

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs) -> bool:
        if HAS_CONVICTION:
            if not check_conviction(self, pair):
                return False
            record_entry_regime(self, pair)
        return True

    def custom_stake_amount(self, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side,
                            **kwargs) -> float:
        if HAS_CONVICTION:
            modifier = get_position_modifier(self, kwargs.get("pair", ""))
            return proposed_stake * modifier
        return proposed_stake

    def custom_stoploss(self, pair, trade, current_time, current_rate,
                        current_profit, after_fill, **kwargs) -> float:
        atr = self.dp.get_pair_dataframe(pair, self.timeframe)["atr"].iloc[-1]
        regime_mult = 1.0
        if HAS_CONVICTION:
            regime_mult = get_regime_stop_multiplier(self, pair)

        atr_stop = (atr / current_rate) * self.atr_multiplier.value * regime_mult
        stop = -atr_stop

        # Tighten at profit thresholds
        if current_profit > 0.03:
            stop = max(stop, -0.025)
        if current_profit > 0.05:
            stop = max(stop, -0.015)

        return stop

    def custom_exit(self, pair, trade, current_time, current_rate,
                    current_profit, **kwargs):
        if HAS_CONVICTION:
            advice = check_exit_advice(self, pair, trade, current_time, current_profit)
            if advice:
                return advice
        return None
