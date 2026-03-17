"""MomentumScalper15m — Sub-hourly momentum scalping.

15m timeframe with 1h informative pairs for regime context.
Fast EMAs (9/21), tight targets, tight stops.
Top 5 pairs by volume only (manage processing load).
"""

import logging

import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy, informative
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


class MomentumScalper15m(IStrategy):
    """15-minute momentum scalper with fast EMA crossover entries."""

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True
    startup_candle_count = 100

    stoploss = -0.015
    use_custom_stoploss = True

    minimal_roi = {
        "0": 0.008,
        "15": 0.005,
        "45": 0.003,
    }

    # Hyperopt parameters
    buy_ema_fast = IntParameter(5, 15, default=9, space="buy")
    buy_ema_slow = IntParameter(15, 30, default=21, space="buy")
    buy_rsi_threshold = IntParameter(30, 50, default=40, space="buy")
    buy_volume_factor = DecimalParameter(0.8, 3.0, default=1.5, space="buy")
    sell_rsi_threshold = IntParameter(60, 85, default=70, space="sell")
    atr_multiplier = DecimalParameter(0.5, 2.0, default=1.0, space="buy")

    @informative("1h")
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """1h informative for regime context."""
        dataframe["ema_50_1h"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["adx_1h"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["rsi_1h"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.buy_ema_fast.value)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.buy_ema_slow.value)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd_hist"] = macd["macdhist"]
        dataframe["macd_hist_prev"] = dataframe["macd_hist"].shift(1)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["volume_sma"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_sma"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long: fast EMA crosses above slow + momentum confirmation
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                & (dataframe["rsi"] > self.buy_rsi_threshold.value)
                & (dataframe["rsi"] < 75)
                & (dataframe["volume_ratio"] > self.buy_volume_factor.value)
                & (dataframe["adx"] > 15)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        # Short: fast EMA crosses below slow + bearish momentum
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
                & (dataframe["rsi"] < (100 - self.buy_rsi_threshold.value))
                & (dataframe["rsi"] > 25)
                & (dataframe["volume_ratio"] > self.buy_volume_factor.value)
                & (dataframe["adx"] > 15)
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit long: RSI overbought or EMA cross back
        dataframe.loc[
            (
                (dataframe["rsi"] > self.sell_rsi_threshold.value)
                | (dataframe["ema_fast"] < dataframe["ema_slow"])
            ),
            "exit_long",
        ] = 1

        # Exit short: RSI oversold or EMA cross back
        dataframe.loc[
            (
                (dataframe["rsi"] < (100 - self.sell_rsi_threshold.value))
                | (dataframe["ema_fast"] > dataframe["ema_slow"])
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

        if current_profit > 0.005:
            stop = max(stop, -0.008)
        if current_profit > 0.008:
            stop = max(stop, -0.004)

        return stop

    def custom_exit(self, pair, trade, current_time, current_rate,
                    current_profit, **kwargs):
        if HAS_CONVICTION:
            advice = check_exit_advice(self, pair, trade, current_time, current_profit)
            if advice:
                return advice
        return None
