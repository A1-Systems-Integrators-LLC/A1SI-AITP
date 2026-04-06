"""BollingerMeanReversion — Freqtrade Strategy
=============================================
Mean-reversion strategy using Bollinger Bands with volume and RSI confirmation.

Logic:
    ENTRY (Long):
        - Price closes below lower Bollinger Band (2 std dev)
        - RSI < 40 (oversold confirmation)
        - Volume spike (volume > 1.2x 20-period average) — validates institutional interest
        - ADX < 35 (ranging/weak-trend market, where mean-reversion works)

    EXIT:
        - Price reaches Bollinger middle band (SMA 20)
        - RSI > 65
        - Tiered ROI

LEARNING PHASE: Conviction/risk gates DISABLED to observe raw strategy behavior.
Best suited for ranging/consolidating markets.
"""

import logging
import os
from datetime import datetime
from functools import reduce

import talib.abstract as ta
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
    IStrategy,
)
from pandas import DataFrame

logger = logging.getLogger(__name__)

# ── Learning phase: conviction system disabled ──
# Re-enable after 2+ weeks of observing raw strategy signal quality.
LEARNING_PHASE = True


class BollingerMeanReversion(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    # Warm-up: BB period up to 30, plus RSI/ADX/ATR 14 — need at least 30 candles.
    startup_candle_count = 50

    # ── Risk API integration (disabled during learning phase) ──
    risk_api_url = os.environ.get("RISK_API_URL", "http://127.0.0.1:8000")
    risk_portfolio_id = 1

    minimal_roi = {
        "0": 0.06,
        "60": 0.03,
        "120": 0.015,
        "240": 0.008,
    }

    stoploss = -0.03
    use_custom_stoploss = True
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.01
    trailing_only_offset_is_reached = True

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": True,
    }

    # ── Parameters — fixed for learning phase (2026-04-06) ──
    # BB std 2.0: standard 2-sigma band, proven mean-reversion level
    # RSI 40: generous enough to catch pullbacks, not so loose it's noise
    # Volume 1.2x: re-enabled — confirms real selling pressure at the band
    # ADX 35: ranging-to-moderate trend only (mean-reversion needs range)
    buy_bb_period = IntParameter(15, 30, default=20, space="buy", optimize=True)
    buy_bb_std = DecimalParameter(0.8, 3.0, default=2.0, decimals=1, space="buy", optimize=True)
    buy_rsi_threshold = IntParameter(25, 50, default=40, space="buy", optimize=True)
    buy_volume_factor = DecimalParameter(
        0.5, 2.5, default=1.2, decimals=1, space="buy", optimize=True,
    )
    buy_adx_ceiling = IntParameter(25, 60, default=35, space="buy", optimize=True)
    sell_rsi_threshold = IntParameter(55, 75, default=65, space="sell", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        from freqtrade.enums import RunMode

        # Full BB grid only needed for hyperopt optimization
        if self.dp and self.dp.runmode == RunMode.HYPEROPT:
            for period in range(15, 31):
                for std_x10 in range(8, 31):  # 0.8 to 3.0 in 0.1 steps
                    std = std_x10 / 10.0
                    suffix = f"_{period}_{str(std).replace('.', '')}"
                    bollinger = ta.BBANDS(dataframe, timeperiod=period, nbdevup=std, nbdevdn=std)
                    dataframe[f"bb_upper{suffix}"] = bollinger["upperband"]
                    dataframe[f"bb_mid{suffix}"] = bollinger["middleband"]
                    dataframe[f"bb_lower{suffix}"] = bollinger["lowerband"]
        else:
            # Compute only the selected BB params (saves 95% CPU outside hyperopt)
            period = self.buy_bb_period.value
            std = float(self.buy_bb_std.value)
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
        """Mean-reversion entries: price at lower BB + RSI oversold + volume confirms."""
        std_str = str(float(self.buy_bb_std.value)).replace(".", "")
        bb_suffix = f"_{self.buy_bb_period.value}_{std_str}"

        conditions = [
            # Price below or near lower Bollinger Band
            dataframe["close"] < dataframe[f"bb_lower{bb_suffix}"],

            # RSI oversold
            dataframe["rsi"] < self.buy_rsi_threshold.value,

            # ADX ceiling — mean-reversion works in ranging markets
            dataframe["adx"] < self.buy_adx_ceiling.value,

            # Not in freefall
            dataframe["rsi"] > 10,

            # Volume confirms selling pressure (ALWAYS required — this validates the setup)
            dataframe["volume_ratio"] > float(self.buy_volume_factor.value),

            # Volume present
            dataframe["volume"] > 0,
        ]

        dataframe.loc[reduce(lambda x, y: x & y, conditions), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        std_str = str(float(self.buy_bb_std.value)).replace(".", "")
        bb_suffix = f"_{self.buy_bb_period.value}_{std_str}"

        conditions = [
            # Price reaches middle band (mean reversion target)
            dataframe["close"] > dataframe[f"bb_mid{bb_suffix}"],

            # RSI shows strength
            dataframe["rsi"] > self.sell_rsi_threshold.value,
        ]

        # Exit on either condition
        dataframe.loc[reduce(lambda x, y: x | y, conditions), "exit_long"] = 1

        return dataframe

    def bot_loop_start(self, current_time=None, **kwargs) -> None:
        """Learning phase: no conviction signals fetched."""
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
        """Learning phase: use config stake amount directly."""
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
        """Learning phase: no conviction/risk gates — let every signal through.

        We want to observe raw strategy signal quality without any external
        pipeline blocking trades. This is paper trading with fake money.
        """
        logger.info(
            "ENTRY SIGNAL %s: %s @ %.6f (RSI/BB signal, no gates)",
            pair, side, rate,
        )
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
        """Learning phase: no conviction-based exits — rely on ROI/stoploss/exit_trend."""
        return None

    def custom_stoploss(
        self, pair, trade, current_time, current_rate,
        current_profit, after_fill, **kwargs,
    ):
        """ATR-based dynamic stop loss (no regime dependency)."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr = last_candle.get("atr", 0)
        adx = last_candle.get("adx", 0)
        if atr == 0 or (isinstance(atr, float) and (atr != atr)):
            return self.stoploss

        # Tighter stop in strong trends (ADX > 35) — mean reversion is riskier
        atr_mult = 1.5 if adx > 35 else 2.0
        atr_stop = -(atr * atr_mult) / current_rate

        if current_profit > 0.015:
            atr_stop = max(atr_stop, -0.01)  # Tighten to -1% at 1.5%+
        elif current_profit > 0.008:
            atr_stop = max(atr_stop, -0.02)  # Tighten to -2% at 0.8%+

        return max(atr_stop, self.stoploss)
