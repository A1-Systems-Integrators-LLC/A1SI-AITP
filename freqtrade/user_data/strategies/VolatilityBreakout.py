"""VolatilityBreakout — Freqtrade Strategy (4h timeframe)
=======================================================
Volatility breakout strategy on 4h candles — catches larger momentum expansions.

Uses 4h timeframe for timeframe diversity (BMR=1h, CIV1=1h, VB=4h, Scalper=15m).
4h breakouts are higher conviction and less noisy than 1h breakouts.

Logic:
    ENTRY (Long):
        - Close > N-period high (breakout confirmed)
        - Volume > 1.5x SMA(20) (volume confirms the move)
        - ADX 20-50 and rising (emerging trend, not choppy)
        - RSI 35-70 (fresh move, not already exhausted)

    EXIT:
        - RSI > 80 (exhaustion)
        - OR close crosses below EMA(20) with volume
        - Tiered ROI targets

LEARNING PHASE: Conviction/risk gates DISABLED.
"""

import logging
import os
from datetime import datetime

import talib.abstract as ta
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
    IStrategy,
)
from pandas import DataFrame

logger = logging.getLogger(__name__)

LEARNING_PHASE = True


class VolatilityBreakout(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "4h"  # Changed from 1h for timeframe diversity
    can_short = False
    startup_candle_count = 80

    # ── Risk API (disabled during learning phase) ──
    risk_api_url = os.environ.get("RISK_API_URL", "http://127.0.0.1:8000")
    risk_portfolio_id = 1

    minimal_roi = {
        "0": 0.10,
        "60": 0.06,
        "240": 0.03,
        "720": 0.015,
    }

    stoploss = -0.04  # 4h candles need slightly wider stop
    use_custom_stoploss = True

    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": True,
    }

    # ── Parameters — fixed for learning phase (2026-04-06) ──
    # 4h breakouts: longer period (20), need real volume (1.5x), clean ADX range
    breakout_period = IntParameter(10, 30, default=20, space="buy", optimize=True)
    volume_factor = DecimalParameter(0.8, 3.0, default=1.5, decimals=1, space="buy", optimize=True)
    adx_low = IntParameter(5, 30, default=20, space="buy", optimize=True)
    adx_high = IntParameter(25, 65, default=50, space="buy", optimize=True)
    rsi_low = IntParameter(20, 40, default=35, space="buy", optimize=True)
    rsi_high = IntParameter(65, 80, default=70, space="buy", optimize=True)
    sell_rsi_threshold = IntParameter(75, 95, default=80, space="sell", optimize=True)
    atr_multiplier = DecimalParameter(1.0, 3.5, default=2.5, decimals=1, space="buy", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        from freqtrade.enums import RunMode

        # N-period high/low for breakout detection
        if self.dp and self.dp.runmode == RunMode.HYPEROPT:
            for period in range(10, 31):
                dataframe[f"high_{period}"] = dataframe["high"].rolling(window=period).max()
                dataframe[f"low_{period}"] = dataframe["low"].rolling(window=period).min()
        else:
            period = self.breakout_period.value
            dataframe[f"high_{period}"] = dataframe["high"].rolling(window=period).max()
            dataframe[f"low_{period}"] = dataframe["low"].rolling(window=period).min()

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # ADX (trend strength — we want emerging trend, 15-25 range)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # Bollinger Bands (for width expansion detection)
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bollinger["upperband"]
        dataframe["bb_mid"] = bollinger["middleband"]
        dataframe["bb_lower"] = bollinger["lowerband"]
        bb_range = dataframe["bb_upper"] - dataframe["bb_lower"]
        dataframe["bb_width"] = bb_range / dataframe["bb_mid"]
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
        """Breakout entries: price breaks N-period high + volume + rising ADX."""
        # Required: breakout above N-period high
        breakout = dataframe["close"] > dataframe[f"high_{self.breakout_period.value}"].shift(1)

        # Required: volume confirms the breakout
        vol_confirm = dataframe["volume_ratio"] > float(self.volume_factor.value)

        # ADX confirms trending conditions (minimum threshold only).
        # Previously required ADX in 20-50 range AND rising over 3 candles,
        # which was too strict on 4h — most breakouts happen at ADX > 15.
        adx_ok = dataframe["adx"] >= self.adx_low.value

        # RSI in acceptable range (not already exhausted)
        rsi_ok = (
            (dataframe["rsi"] >= self.rsi_low.value)
            & (dataframe["rsi"] <= self.rsi_high.value)
        )

        has_volume = dataframe["volume"] > 0

        dataframe.loc[
            breakout & vol_confirm & adx_ok & rsi_ok & has_volume,
            "enter_long",
        ] = 1

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

    def bot_loop_start(self, current_time=None, **kwargs) -> None:
        """Learning phase: no conviction signals."""
        pass

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """Learning phase: use config stake amount."""
        return proposed_stake

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        """Learning phase: no gates."""
        logger.info("ENTRY SIGNAL %s: %s @ %.6f (breakout, no gates)", pair, side, rate)
        return True

    def custom_exit(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | None:
        """Learning phase: rely on ROI/stoploss/exit_trend."""
        return None

    def custom_stoploss(
        self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs,
    ):
        """ATR-based dynamic stop loss (no regime dependency)."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr = last_candle.get("atr", 0)
        if atr == 0 or (isinstance(atr, float) and (atr != atr)):
            return self.stoploss

        atr_stop = -(atr * float(self.atr_multiplier.value)) / current_rate

        if current_profit > 0.03:
            atr_stop = max(atr_stop, -0.015)
        elif current_profit > 0.015:
            atr_stop = max(atr_stop, -0.025)

        return max(atr_stop, self.stoploss)
