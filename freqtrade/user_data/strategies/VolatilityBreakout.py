"""
VolatilityBreakout — Freqtrade Strategy
========================================
Volatility breakout strategy that catches momentum expansions.

Complements CryptoInvestorV1 (trend-following) and BollingerMeanReversion
(range-bound). Designed for transitional periods when volatility is
expanding and a new directional move is beginning.

Logic:
    ENTRY (Long):
        - Close > N-period high (breakout)
        - Volume > factor * SMA(20) (volume confirmation)
        - BB width expanding (volatility expanding)
        - ADX 15-25 rising (trend emerging, not yet strong)
        - RSI 40-70 (not oversold/overbought — fresh move)

    EXIT:
        - RSI > 85 (exhaustion)
        - OR close crosses below EMA(20) with volume
        - Tiered ROI targets
        - Hard stop -3% (breakouts fail fast)

Risk Management:
    - 3% hard stop (breakouts that fail, fail fast)
    - ATR-based dynamic stop
    - Trailing stop at 2% profit / 4% offset
    - Maximum 5 concurrent trades
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


class VolatilityBreakout(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    # Warm-up: breakout period up to 30, EMA 50, plus BB/RSI/ADX/ATR.
    startup_candle_count = 80

    # ── Risk API integration ──
    risk_api_url = "http://127.0.0.1:8000"
    risk_portfolio_id = 1

    minimal_roi = {
        "0": 0.08,     # 8% ROI target
        "60": 0.05,    # 5% after 1 hour
        "180": 0.03,   # 3% after 3 hours
        "360": 0.015,  # 1.5% after 6 hours
    }

    stoploss = -0.03  # -3% hard stop (breakouts fail fast)
    use_custom_stoploss = True

    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.04
    trailing_only_offset_is_reached = True

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Hyperopt parameters
    breakout_period = IntParameter(10, 30, default=20, space="buy", optimize=True)
    volume_factor = DecimalParameter(1.2, 3.0, default=1.8, decimals=1, space="buy", optimize=True)
    adx_low = IntParameter(10, 20, default=15, space="buy", optimize=True)
    adx_high = IntParameter(20, 35, default=25, space="buy", optimize=True)
    rsi_low = IntParameter(35, 50, default=40, space="buy", optimize=True)
    rsi_high = IntParameter(60, 75, default=70, space="buy", optimize=True)
    sell_rsi_threshold = IntParameter(80, 95, default=85, space="sell", optimize=True)
    adx_tolerance = DecimalParameter(0.0, 1.5, default=0.5, decimals=1, space="buy", optimize=True)
    atr_multiplier = DecimalParameter(1.0, 2.5, default=1.5, decimals=1, space="buy", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # N-period high for breakout detection (multiple periods for optimization)
        for period in [10, 15, 20, 25, 30]:
            dataframe[f"high_{period}"] = dataframe["high"].rolling(window=period).max()

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # ADX (trend strength — we want emerging trend, 15-25 range)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["adx_prev"] = dataframe["adx"].shift(1)

        # Bollinger Bands (for width expansion detection)
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bollinger["upperband"]
        dataframe["bb_mid"] = bollinger["middleband"]
        dataframe["bb_lower"] = bollinger["lowerband"]
        dataframe["bb_width"] = (dataframe["bb_upper"] - dataframe["bb_lower"]) / dataframe["bb_mid"]
        dataframe["bb_width_prev"] = dataframe["bb_width"].shift(1)

        # EMAs
        dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)

        # ATR for dynamic stops
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # Volume
        dataframe["volume_sma_20"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_sma_20"]

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        conditions = [
            # Breakout: close above N-period high (shifted to avoid lookahead)
            dataframe["close"] > dataframe[f"high_{self.breakout_period.value}"].shift(1),

            # Volume confirmation
            dataframe["volume_ratio"] > float(self.volume_factor.value),

            # BB width expanding (volatility increasing)
            dataframe["bb_width"] > dataframe["bb_width_prev"],

            # ADX in emerging-trend range and rising
            dataframe["adx"] >= self.adx_low.value,
            dataframe["adx"] <= self.adx_high.value,
            dataframe["adx"] > dataframe["adx_prev"] - self.adx_tolerance.value,

            # RSI in neutral zone (fresh move, not exhausted)
            dataframe["rsi"] >= self.rsi_low.value,
            dataframe["rsi"] <= self.rsi_high.value,

            # Volume present
            dataframe["volume"] > 0,
        ]

        dataframe.loc[reduce(lambda x, y: x & y, conditions), "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # Exit on exhaustion or trend failure
        exit_rsi = dataframe["rsi"] > self.sell_rsi_threshold.value

        exit_ema_cross = (
            (dataframe["close"] < dataframe["ema_20"])
            & (dataframe["close"].shift(1) >= dataframe["ema_20"].shift(1))
            & (dataframe["volume_ratio"] > 1.0)
        )

        dataframe.loc[exit_rsi | exit_ema_cross, "exit_long"] = 1
        return dataframe

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
        """Gate trades through the backend risk API (fail-safe: reject).

        In backtesting/hyperopt mode, skip the API call since the backend
        may not be running and risk checks are not meaningful for historical sims.
        """
        from freqtrade.enums import RunMode

        if self.dp and self.dp.runmode in (RunMode.BACKTEST, RunMode.HYPEROPT):
            return True

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

    def custom_stoploss(
        self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs
    ):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr = last_candle.get("atr", 0)
        if atr == 0:
            return self.stoploss

        # ATR-based stop distance
        atr_stop = -(atr * float(self.atr_multiplier.value)) / current_rate

        # Tighten as profit increases (breakouts: protect gains quickly)
        if current_profit > 0.05:
            atr_stop = max(atr_stop, -0.015)  # Tight at 5%+
        elif current_profit > 0.03:
            atr_stop = max(atr_stop, -0.02)   # Moderate at 3%+

        return max(atr_stop, self.stoploss)
