"""TrendReversal — Regime transition hunter.

Targets regime transitions: STRONG_TREND_DOWN → RANGING = potential bottom.
RSI divergence detection + MACD confirmation + volume surge.
Strong where other strategies are weak (STD, HV regimes).
"""

import logging

import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

logger = logging.getLogger(__name__)

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


class TrendReversal(IStrategy):
    """Regime transition strategy targeting trend exhaustion and reversals."""

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    startup_candle_count = 100

    stoploss = -0.06
    use_custom_stoploss = True

    minimal_roi = {
        "0": 0.06,
        "120": 0.04,
        "360": 0.025,
        "720": 0.01,
    }

    # Hyperopt parameters
    buy_rsi_divergence_lookback = IntParameter(5, 20, default=10, space="buy")
    buy_rsi_threshold = IntParameter(20, 40, default=30, space="buy")
    buy_volume_surge = DecimalParameter(1.0, 3.0, default=1.5, space="buy")
    sell_rsi_threshold = IntParameter(60, 80, default=70, space="sell")
    atr_multiplier = DecimalParameter(1.5, 4.0, default=2.5, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Core indicators
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]
        dataframe["macd_hist"] = macd["macdhist"]
        dataframe["macd_hist_prev"] = dataframe["macd_hist"].shift(1)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["adx_prev"] = dataframe["adx"].shift(1)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # EMAs for trend context
        dataframe["ema_21"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_100"] = ta.EMA(dataframe, timeperiod=100)

        # Volume
        dataframe["volume_sma"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_sma"]

        # RSI divergence detection
        lb = self.buy_rsi_divergence_lookback.value

        # Bullish divergence: price making lower low but RSI making higher low
        dataframe["price_low_n"] = dataframe["low"].rolling(lb).min()
        dataframe["rsi_low_n"] = dataframe["rsi"].rolling(lb).min()
        dataframe["price_making_lower_low"] = (
            dataframe["low"] <= dataframe["price_low_n"].shift(1)
        )
        dataframe["rsi_making_higher_low"] = (
            dataframe["rsi"] > dataframe["rsi_low_n"].shift(1)
        )
        dataframe["bullish_divergence"] = (
            dataframe["price_making_lower_low"] & dataframe["rsi_making_higher_low"]
        )

        # Bearish divergence: price making higher high but RSI making lower high
        dataframe["price_high_n"] = dataframe["high"].rolling(lb).max()
        dataframe["rsi_high_n"] = dataframe["rsi"].rolling(lb).max()
        dataframe["price_making_higher_high"] = (
            dataframe["high"] >= dataframe["price_high_n"].shift(1)
        )
        dataframe["rsi_making_lower_high"] = (
            dataframe["rsi"] < dataframe["rsi_high_n"].shift(1)
        )
        dataframe["bearish_divergence"] = (
            dataframe["price_making_higher_high"] & dataframe["rsi_making_lower_high"]
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long: bullish divergence + MACD turning up + volume surge
        # Targets bottom fishing after downtrend exhaustion
        dataframe.loc[
            (
                (dataframe["bullish_divergence"])
                & (dataframe["macd_hist"] > dataframe["macd_hist_prev"])
                & (dataframe["rsi"] < self.buy_rsi_threshold.value + 15)
                & (dataframe["volume_ratio"] > self.buy_volume_surge.value)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        # Short: bearish divergence + MACD turning down + volume surge
        # Targets top reversal after uptrend exhaustion
        dataframe.loc[
            (
                (dataframe["bearish_divergence"])
                & (dataframe["macd_hist"] < dataframe["macd_hist_prev"])
                & (dataframe["rsi"] > self.sell_rsi_threshold.value - 15)
                & (dataframe["volume_ratio"] > self.buy_volume_surge.value)
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit long: RSI overbought or trend fully reversed (crossed above EMA50)
        dataframe.loc[
            (
                (dataframe["rsi"] > self.sell_rsi_threshold.value)
                | (
                    (dataframe["close"] > dataframe["ema_50"])
                    & (dataframe["close"].shift(1) < dataframe["ema_50"].shift(1))
                )
            ),
            "exit_long",
        ] = 1

        # Exit short: RSI oversold or trend reversed down (crossed below EMA50)
        dataframe.loc[
            (
                (dataframe["rsi"] < (100 - self.sell_rsi_threshold.value))
                | (
                    (dataframe["close"] < dataframe["ema_50"])
                    & (dataframe["close"].shift(1) > dataframe["ema_50"].shift(1))
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

        if current_profit > 0.04:
            stop = max(stop, -0.03)
        if current_profit > 0.06:
            stop = max(stop, -0.02)

        return stop

    def custom_exit(self, pair, trade, current_time, current_rate,
                    current_profit, **kwargs):
        if HAS_CONVICTION:
            advice = check_exit_advice(self, pair, trade, current_time, current_profit)
            if advice:
                return advice
        return None
