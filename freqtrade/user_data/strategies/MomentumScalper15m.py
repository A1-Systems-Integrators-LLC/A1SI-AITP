"""MomentumScalper15m — Sub-hourly momentum scalping.

15m timeframe with 1h informative pairs for regime context.
Fast EMAs (9/21), tight targets, tight stops.

LEARNING PHASE: Conviction/risk gates DISABLED.
"""

import logging

import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy, informative
from pandas import DataFrame

logger = logging.getLogger(__name__)

LEARNING_PHASE = True


class MomentumScalper15m(IStrategy):
    """15-minute momentum scalper with fast EMA crossover entries."""

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = False  # Kraken spot only — short signals ignored until futures exchange added
    startup_candle_count = 100

    stoploss = -0.10
    use_custom_stoploss = True

    minimal_roi = {
        "0": 0.02,
        "15": 0.012,
        "45": 0.006,
        "90": 0.003,
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
        # Long: fast EMA above slow with recent crossover (within 3 candles).
        # The crossover persistence window avoids missing signals that only
        # fire on the exact crossover bar (1 candle = 15 min, easily missed).
        crossover_long = (
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
        )
        recent_crossover_long = (
            crossover_long
            | crossover_long.shift(1).fillna(False)
            | crossover_long.shift(2).fillna(False)
        )
        dataframe.loc[
            (
                recent_crossover_long
                & (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["rsi"] > self.buy_rsi_threshold.value)
                & (dataframe["rsi"] < 75)
                & (dataframe["volume_ratio"] > self.buy_volume_factor.value)
                & (dataframe["adx"] > 15)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        # Short: fast EMA below slow with recent crossover (within 3 candles)
        crossover_short = (
            (dataframe["ema_fast"] < dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
        )
        recent_crossover_short = (
            crossover_short
            | crossover_short.shift(1).fillna(False)
            | crossover_short.shift(2).fillna(False)
        )
        dataframe.loc[
            (
                recent_crossover_short
                & (dataframe["ema_fast"] < dataframe["ema_slow"])
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
        # Exit long: RSI overbought AND EMA cross back (both must confirm reversal)
        # Previously used OR which exited on any single-candle EMA wiggle
        dataframe.loc[
            (
                (dataframe["rsi"] > self.sell_rsi_threshold.value)
                & (dataframe["ema_fast"] < dataframe["ema_slow"])
            ),
            "exit_long",
        ] = 1

        # Exit short: RSI oversold AND EMA cross back
        dataframe.loc[
            (
                (dataframe["rsi"] < (100 - self.sell_rsi_threshold.value))
                & (dataframe["ema_fast"] > dataframe["ema_slow"])
            ),
            "exit_short",
        ] = 1

        return dataframe

    def custom_leverage(self, pair: str, current_time, current_rate, proposed_leverage,
                        max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3.0, max_leverage)

    def bot_loop_start(self, **kwargs) -> None:
        """Learning phase: no conviction signals."""
        pass

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs) -> bool:
        """Learning phase: no gates."""
        logger.info("ENTRY SIGNAL %s: %s @ %.6f (scalp, no gates)", pair, side, rate)
        return True

    def custom_stake_amount(self, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side,
                            **kwargs) -> float:
        return proposed_stake

    def custom_stoploss(self, pair, trade, current_time, current_rate,
                        current_profit, after_fill, **kwargs) -> float:
        atr = self.dp.get_pair_dataframe(pair, self.timeframe)["atr"].iloc[-1]

        atr_stop = (atr / current_rate) * self.atr_multiplier.value
        stop = -atr_stop

        # Wider trailing stops — let winners breathe on volatile 15m candles.
        # Old: tightened to -0.8% at 0.5% profit, -0.4% at 0.8% — too tight,
        # normal 15m volatility (0.5-1.0%) would stop out every winning trade.
        if current_profit > 0.01:
            stop = max(stop, -0.006)
        if current_profit > 0.02:
            stop = max(stop, -0.003)

        return stop

    def custom_exit(self, pair, trade, current_time, current_rate,
                    current_profit, **kwargs):
        """Learning phase: rely on ROI/stoploss/exit_trend."""
        return None
