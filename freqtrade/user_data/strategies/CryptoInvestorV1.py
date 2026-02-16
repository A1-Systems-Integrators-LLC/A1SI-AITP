"""
CryptoInvestorStrategy v1 — Freqtrade Strategy
=================================================
Trend-following strategy using EMA alignment + RSI pullback entries.

Logic:
    ENTRY (Long):
        - Price above EMA 50 AND EMA 50 above EMA 200 (uptrend confirmed)
        - RSI 14 pulls back below 40 (momentum reset in uptrend)
        - Volume above 20-period SMA (confirming interest)
        - MACD histogram > 0 or turning positive (momentum confirmation)

    EXIT:
        - ROI targets (tiered)
        - Trailing stop loss (ATR-based)
        - RSI > 80 (overbought exit)
        - Price closes below EMA 50 (trend breakdown)

Risk Management:
    - ATR-based stop loss (2x ATR below entry)
    - Trailing stop activates at 3% profit
    - Maximum 5 concurrent trades
"""

import logging
from datetime import datetime, timedelta, timezone
from functools import reduce
from typing import Optional

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import (
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    IStrategy,
    merge_informative_pair,
)

logger = logging.getLogger(__name__)


class CryptoInvestorV1(IStrategy):
    """
    Trend-following strategy with RSI pullback entries.

    Designed for spot crypto trading on 1h timeframe.
    """

    # ── Strategy metadata ──
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False

    # ── Risk API integration ──
    risk_api_url = "http://127.0.0.1:8000"
    risk_portfolio_id = 1

    # ── ROI table ──
    minimal_roi = {
        "0": 0.10,     # 10% ROI target
        "60": 0.06,    # 6% after 1 hour
        "240": 0.03,   # 3% after 4 hours
        "720": 0.01,   # 1% after 12 hours
    }

    # ── Stop loss ──
    stoploss = -0.05  # -5% hard stop loss (ATR-based custom stop is primary)

    # ── Trailing stop ──
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.035
    trailing_only_offset_is_reached = True

    # ── Order settings ──
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # ── Hyperopt parameters ──
    buy_ema_fast = IntParameter(20, 80, default=50, space="buy", optimize=True)
    buy_ema_slow = IntParameter(100, 300, default=200, space="buy", optimize=True)
    buy_rsi_threshold = IntParameter(25, 45, default=40, space="buy", optimize=True)
    sell_rsi_threshold = IntParameter(70, 90, default=80, space="sell", optimize=True)
    atr_multiplier = DecimalParameter(1.5, 3.5, default=2.0, decimals=1, space="buy", optimize=True)

    # ── Informative pairs ──
    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all technical indicators."""

        # ── Moving Averages ──
        for period in [7, 14, 21, 50, 100, 200]:
            dataframe[f"ema_{period}"] = ta.EMA(dataframe, timeperiod=period)
            dataframe[f"sma_{period}"] = ta.SMA(dataframe, timeperiod=period)

        # ── RSI ──
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # ── MACD ──
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # ── Bollinger Bands ──
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bollinger["upperband"]
        dataframe["bb_mid"] = bollinger["middleband"]
        dataframe["bb_lower"] = bollinger["lowerband"]
        dataframe["bb_width"] = (dataframe["bb_upper"] - dataframe["bb_lower"]) / dataframe["bb_mid"]

        # ── ATR ──
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # ── Volume ──
        dataframe["volume_sma_20"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_sma_20"]

        # ── Stochastic ──
        stoch = ta.STOCH(dataframe)
        dataframe["stoch_k"] = stoch["slowk"]
        dataframe["stoch_d"] = stoch["slowd"]

        # ── ADX (trend strength) ──
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # ── Trend alignment flags ──
        dataframe["uptrend"] = (
            (dataframe["ema_50"] > dataframe["ema_200"]) &
            (dataframe["close"] > dataframe["ema_50"])
        ).astype(int)

        dataframe["strong_uptrend"] = (
            (dataframe["ema_21"] > dataframe["ema_50"]) &
            (dataframe["ema_50"] > dataframe["ema_200"]) &
            (dataframe["close"] > dataframe["ema_21"]) &
            (dataframe["adx"] > 25)
        ).astype(int)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Define entry (buy) conditions."""

        conditions = []

        # Condition 1: Price in uptrend (EMA alignment)
        conditions.append(
            (dataframe["close"] > dataframe[f"ema_{self.buy_ema_fast.value}"]) &
            (dataframe[f"ema_{self.buy_ema_fast.value}"] > dataframe[f"ema_{self.buy_ema_slow.value}"])
        )

        # Condition 2: RSI pullback in uptrend
        conditions.append(dataframe["rsi"] < self.buy_rsi_threshold.value)

        # Condition 3: Volume confirmation
        conditions.append(dataframe["volume_ratio"] > 0.8)

        # Condition 4: MACD momentum (histogram positive or turning)
        conditions.append(
            (dataframe["macdhist"] > 0) |
            (dataframe["macdhist"] > dataframe["macdhist"].shift(1))
        )

        # Condition 5: Not near Bollinger upper band (avoid chasing)
        conditions.append(
            dataframe["close"] < dataframe["bb_upper"] * 0.98
        )

        # Condition 6: Basic volume filter
        conditions.append(dataframe["volume"] > 0)

        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Define exit (sell) conditions."""

        conditions = []

        # Exit 1: RSI overbought
        conditions.append(dataframe["rsi"] > self.sell_rsi_threshold.value)

        # Exit 2: Price closes below fast EMA (trend weakening)
        exit_trend_break = (
            (dataframe["close"] < dataframe[f"ema_{self.buy_ema_fast.value}"]) &
            (dataframe["close"].shift(1) >= dataframe[f"ema_{self.buy_ema_fast.value}"].shift(1))
        )

        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x | y, conditions) | exit_trend_break,
                "exit_long"
            ] = 1

        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float:
        """
        ATR-based dynamic stop loss.

        - Initial: 2x ATR below entry
        - Tightens as profit increases
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        if dataframe.empty:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr = last_candle.get("atr", 0)

        if atr == 0:
            return self.stoploss

        # ATR-based stop distance
        atr_stop = -(atr * float(self.atr_multiplier.value)) / current_rate

        # Tighten stop as profit increases
        if current_profit > 0.06:
            atr_stop = max(atr_stop, -0.02)  # Tighten to -2%
        elif current_profit > 0.03:
            atr_stop = max(atr_stop, -0.03)  # Tighten to -3%

        return max(atr_stop, self.stoploss)

    def custom_exit(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> Optional[str]:
        """Custom exit logic for specific conditions."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        if dataframe.empty:
            return None

        last_candle = dataframe.iloc[-1]

        # Exit if trend fully breaks down (EMAs cross bearish)
        if (
            last_candle.get(f"ema_{self.buy_ema_fast.value}", 0)
            < last_candle.get(f"ema_{self.buy_ema_slow.value}", 0)
            and current_profit > -0.02
        ):
            return "trend_breakdown"

        # Exit if held too long with small profit (opportunity cost)
        if trade.open_date_utc + timedelta(days=7) < current_time:
            if current_profit < 0.01:
                return "stale_trade"

        return None

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        """Gate trades through the backend risk API (fail-safe: reject)."""
        try:
            import requests

            stop_loss_price = rate * (1 + self.stoploss)  # stoploss is negative
            resp = requests.post(
                f"{self.risk_api_url}/api/risk/{self.risk_portfolio_id}/check-trade",
                json={
                    "symbol": pair,
                    "side": side,
                    "size": amount,
                    "entry_price": rate,
                    "stop_loss_price": stop_loss_price,
                },
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("approved", False):
                    logger.warning(f"Risk gate REJECTED {pair}: {data.get('reason')}")
                    return False
                logger.info(f"Risk gate approved {pair}")
                return True
            logger.warning(f"Risk API returned {resp.status_code}, rejecting trade")
            return False
        except Exception as e:
            logger.error(f"Risk API unreachable ({e}), rejecting trade")
            return False
