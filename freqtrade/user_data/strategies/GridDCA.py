"""GridDCA — Grid trading with DCA for ranging markets.

Captures value in RANGING regimes (4/7 regimes currently wasted by other strategies).
Long below BB mid, short above BB mid. Requires ADX < 25.
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


class GridDCA(IStrategy):
    """Grid trading strategy for ranging/sideways markets with DCA multiplier."""

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    startup_candle_count = 50

    stoploss = -0.04
    use_custom_stoploss = True

    minimal_roi = {
        "0": 0.025,
        "60": 0.015,
        "240": 0.008,
        "480": 0.003,
    }

    position_adjustment_enable = True

    # Hyperopt parameters
    buy_bb_period = IntParameter(15, 30, default=20, space="buy")
    buy_bb_std = DecimalParameter(1.0, 3.0, default=2.0, space="buy")
    buy_adx_ceiling = IntParameter(15, 35, default=25, space="buy")
    buy_rsi_low = IntParameter(20, 40, default=30, space="buy")
    buy_rsi_high = IntParameter(60, 80, default=70, space="buy")
    atr_multiplier = DecimalParameter(1.0, 2.5, default=1.5, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bb = ta.BBANDS(dataframe, timeperiod=self.buy_bb_period.value,
                       nbdevup=self.buy_bb_std.value, nbdevdn=self.buy_bb_std.value)
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["bb_middle"] = bb["middleband"]
        dataframe["bb_lower"] = bb["lowerband"]
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["volume_sma"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_sma"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long: price below BB mid in ranging market
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["bb_middle"])
                & (dataframe["close"] > dataframe["bb_lower"])
                & (dataframe["adx"] < self.buy_adx_ceiling.value)
                & (dataframe["rsi"] < self.buy_rsi_high.value)
                & (dataframe["rsi"] > self.buy_rsi_low.value)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        # Short: price above BB mid in ranging market
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["bb_middle"])
                & (dataframe["close"] < dataframe["bb_upper"])
                & (dataframe["adx"] < self.buy_adx_ceiling.value)
                & (dataframe["rsi"] > (100 - self.buy_rsi_high.value))
                & (dataframe["rsi"] < (100 - self.buy_rsi_low.value))
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit long: price reaches BB mid or above
        dataframe.loc[
            (dataframe["close"] >= dataframe["bb_middle"]),
            "exit_long",
        ] = 1

        # Exit short: price drops to BB mid or below
        dataframe.loc[
            (dataframe["close"] <= dataframe["bb_middle"]),
            "exit_short",
        ] = 1

        return dataframe

    def adjust_trade_position(self, trade, current_time, current_rate,
                              current_profit, min_stake, max_stake,
                              current_entry_rate, current_exit_rate,
                              current_entry_profit, current_exit_profit,
                              **kwargs) -> float | None:
        """DCA: add to position if price moves against us in ranging market."""
        if current_profit > -0.02:
            return None  # Only DCA if losing > 2%

        # Check ADX still indicates ranging
        dataframe = self.dp.get_pair_dataframe(trade.pair, self.timeframe)
        if dataframe.empty:
            return None
        adx = dataframe["adx"].iloc[-1]
        if adx > self.buy_adx_ceiling.value + 5:
            return None  # Market broke out of range, don't DCA

        # Add 50% of original stake
        return trade.stake_amount * 0.5

    def custom_leverage(self, pair: str, current_time, current_rate, proposed_leverage,
                        max_leverage, entry_tag, side, **kwargs) -> float:
        return min(2.0, max_leverage)  # Lower leverage for grid trading

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

        if current_profit > 0.015:
            stop = max(stop, -0.02)
        if current_profit > 0.025:
            stop = max(stop, -0.01)

        return stop

    def custom_exit(self, pair, trade, current_time, current_rate,
                    current_profit, **kwargs):
        if HAS_CONVICTION:
            advice = check_exit_advice(self, pair, trade, current_time, current_profit)
            if advice:
                return advice
        return None
