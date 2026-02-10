"""
BollingerMeanReversion — Freqtrade Strategy
=============================================
Mean-reversion strategy using Bollinger Bands with volume and RSI confirmation.

Logic:
    ENTRY (Long):
        - Price closes below lower Bollinger Band (2 std dev)
        - RSI < 35 (oversold confirmation)
        - Volume spike (volume > 1.5x 20-period average)
        - ADX < 30 (ranging market, mean-reversion favorable)

    EXIT:
        - Price reaches Bollinger middle band (SMA 20)
        - RSI > 65
        - Tiered ROI

Best suited for ranging/consolidating markets. Paired with trend detection
to automatically disable in strong trending conditions.
"""

import logging
from functools import reduce
from typing import Optional
from datetime import datetime

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
    IStrategy,
)

logger = logging.getLogger(__name__)


class BollingerMeanReversion(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False

    minimal_roi = {
        "0": 0.06,
        "60": 0.04,
        "240": 0.02,
        "480": 0.01,
    }

    stoploss = -0.04
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.025
    trailing_only_offset_is_reached = True

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Hyperopt parameters
    buy_bb_period = IntParameter(15, 30, default=20, space="buy", optimize=True)
    buy_bb_std = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="buy", optimize=True)
    buy_rsi_threshold = IntParameter(25, 40, default=35, space="buy", optimize=True)
    buy_volume_factor = DecimalParameter(1.0, 2.5, default=1.5, decimals=1, space="buy", optimize=True)
    sell_rsi_threshold = IntParameter(55, 75, default=65, space="sell", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # Bollinger Bands (multiple periods for optimization)
        for period in [15, 20, 25, 30]:
            for std in [1.5, 2.0, 2.5, 3.0]:
                suffix = f"_{period}_{str(std).replace('.', '')}"
                bollinger = ta.BBANDS(dataframe, timeperiod=period, nbdevup=std, nbdevdn=std)
                dataframe[f"bb_upper{suffix}"] = bollinger["upperband"]
                dataframe[f"bb_mid{suffix}"] = bollinger["middleband"]
                dataframe[f"bb_lower{suffix}"] = bollinger["lowerband"]

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # ADX (trend strength — low ADX = ranging)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # Volume
        dataframe["volume_sma_20"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_sma_20"]

        # ATR for dynamic stops
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # Stochastic for additional confirmation
        stoch = ta.STOCH(dataframe)
        dataframe["stoch_k"] = stoch["slowk"]
        dataframe["stoch_d"] = stoch["slowd"]

        # MFI (Money Flow Index)
        dataframe["mfi"] = ta.MFI(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        bb_suffix = f"_{self.buy_bb_period.value}_{str(float(self.buy_bb_std.value)).replace('.', '')}"

        conditions = [
            # Price below lower Bollinger Band
            dataframe["close"] < dataframe[f"bb_lower{bb_suffix}"],

            # RSI oversold
            dataframe["rsi"] < self.buy_rsi_threshold.value,

            # Volume spike
            dataframe["volume_ratio"] > float(self.buy_volume_factor.value),

            # Ranging market (low ADX = mean reversion more likely to work)
            dataframe["adx"] < 30,

            # Not in extreme downtrend (some floor)
            dataframe["rsi"] > 10,

            # Volume present
            dataframe["volume"] > 0,
        ]

        dataframe.loc[reduce(lambda x, y: x & y, conditions), "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        bb_suffix = f"_{self.buy_bb_period.value}_{str(float(self.buy_bb_std.value)).replace('.', '')}"

        conditions = [
            # Price reaches middle band (mean reversion target)
            dataframe["close"] > dataframe[f"bb_mid{bb_suffix}"],

            # RSI shows strength
            dataframe["rsi"] > self.sell_rsi_threshold.value,
        ]

        # Exit on either condition
        dataframe.loc[reduce(lambda x, y: x | y, conditions), "exit_long"] = 1
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr = last_candle.get("atr", 0)
        if atr == 0:
            return self.stoploss

        # 1.5x ATR stop for mean-reversion (tighter than trend following)
        atr_stop = -(atr * 1.5) / current_rate

        if current_profit > 0.03:
            atr_stop = max(atr_stop, -0.015)
        elif current_profit > 0.015:
            atr_stop = max(atr_stop, -0.02)

        return max(atr_stop, self.stoploss)
