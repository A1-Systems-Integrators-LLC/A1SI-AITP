"""CryptoInvestorStrategy v1 — Freqtrade Strategy
=================================================
Trend-following dip-buyer: enters on RSI pullbacks within confirmed uptrends.

The KEY INSIGHT is that this is a DIP-BUYER, not a breakout strategy.
In an uptrend (EMA fast > EMA slow), wait for RSI to pull back to 30-45
(price dipped), then buy the dip. Price will naturally be near or slightly
below the fast EMA during a pullback — that's the whole point.

Logic:
    ENTRY (Long):
        - EMA 20 > EMA 50 (uptrend structure confirmed)
        - RSI 14 pulls back to 30-45 (dip in uptrend)
        - MACD histogram improving (momentum recovering)
        - Volume present

    EXIT:
        - ROI targets (tiered)
        - Trailing stop loss (ATR-based)
        - RSI > 80 (overbought exit)
        - EMA cross bearish (trend breakdown)

LEARNING PHASE: Conviction/risk gates DISABLED to observe raw strategy behavior.
"""

import logging
import os
from datetime import datetime, timedelta
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
LEARNING_PHASE = True


class CryptoInvestorV1(IStrategy):
    """Trend-following dip-buyer: RSI pullback entries in confirmed uptrends.

    Designed for spot crypto trading on 1h timeframe.
    """

    # ── Strategy metadata ──
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    # Warm-up: need at least EMA 50 + some buffer.
    startup_candle_count = 80

    # ── Risk API integration (disabled during learning phase) ──
    risk_api_url = os.environ.get("RISK_API_URL", "http://127.0.0.1:8000")
    risk_portfolio_id = 1

    # ── ROI table ──
    minimal_roi = {
        "0": 0.08,
        "120": 0.04,
        "480": 0.02,
        "1440": 0.01,
    }

    # ── Stop loss ──
    stoploss = -0.04
    use_custom_stoploss = True

    # ── Trailing stop ──
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    # ── Order settings ──
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": True,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # ── Parameters — fixed for learning phase (2026-04-06) ──
    # EMA 20/50: standard trend-following pair, not the broken 17/102 combo
    # RSI 45: pullback zone in uptrend (30-45 is where dips happen)
    # Sell RSI 75: take profits before extreme overbought
    # ATR mult 2.5: balanced stop distance
    buy_ema_fast = IntParameter(10, 80, default=20, space="buy", optimize=True)
    buy_ema_slow = IntParameter(50, 300, default=50, space="buy", optimize=True)
    buy_rsi_threshold = IntParameter(25, 55, default=45, space="buy", optimize=True)
    sell_rsi_threshold = IntParameter(65, 90, default=75, space="sell", optimize=True)
    atr_multiplier = DecimalParameter(1.5, 4.0, default=2.5, decimals=1, space="buy", optimize=True)

    # ── Informative pairs ──
    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all technical indicators."""
        from freqtrade.enums import RunMode

        # ── Moving Averages ──
        if self.dp and self.dp.runmode == RunMode.HYPEROPT:
            for period in range(10, 301):
                dataframe[f"ema_{period}"] = ta.EMA(dataframe, timeperiod=period)
        else:
            for period in {self.buy_ema_fast.value, self.buy_ema_slow.value, 20, 21, 50, 200}:
                dataframe[f"ema_{period}"] = ta.EMA(dataframe, timeperiod=period)

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
        bb_range = dataframe["bb_upper"] - dataframe["bb_lower"]
        dataframe["bb_width"] = bb_range / dataframe["bb_mid"]

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
        """Dip-buyer: RSI pullback within a confirmed uptrend.

        The logic is simple and non-contradictory:
        1. Uptrend confirmed: EMA fast > EMA slow (structure)
        2. RSI dipped: price pulled back (RSI 25-45 zone)
        3. MACD recovering: momentum turning back up
        4. NOT requiring price > EMA (that contradicts the pullback!)

        During a pullback in an uptrend, price SHOULD be near/below the
        fast EMA — that's the buying opportunity.
        """
        ema_fast = f"ema_{self.buy_ema_fast.value}"
        ema_slow = f"ema_{self.buy_ema_slow.value}"

        # 1. Uptrend structure: fast EMA above slow EMA
        uptrend = dataframe[ema_fast] > dataframe[ema_slow]

        # 2. RSI pullback: price has dipped (this is the entry trigger)
        rsi_pullback = (
            (dataframe["rsi"] < self.buy_rsi_threshold.value)
            & (dataframe["rsi"] > 15)  # not in freefall
        )

        # 3. MACD recovering: momentum turning back up after the dip
        macd_recovering = dataframe["macdhist"] > dataframe["macdhist"].shift(1)

        # 4. Volume present
        has_volume = dataframe["volume"] > 0

        entry = uptrend & rsi_pullback & macd_recovering & has_volume
        dataframe.loc[entry, "enter_long"] = 1

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
                "exit_long",
            ] = 1

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
        """ATR-based dynamic stop loss (no regime dependency)."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        if dataframe.empty:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr = last_candle.get("atr", 0)

        if atr == 0 or (isinstance(atr, float) and (atr != atr)):
            return self.stoploss

        atr_stop = -(atr * float(self.atr_multiplier.value)) / current_rate

        # Tighten stop as profit increases
        if current_profit > 0.03:
            atr_stop = max(atr_stop, -0.015)
        elif current_profit > 0.02:
            atr_stop = max(atr_stop, -0.025)

        return max(atr_stop, self.stoploss)

    def custom_exit(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | None:
        """Technical exit checks only (no conviction system)."""
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
        if trade.open_date_utc + timedelta(days=5) < current_time and current_profit < 0.005:
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
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        """Learning phase: no conviction/risk gates — let every signal through."""
        logger.info(
            "ENTRY SIGNAL %s: %s @ %.6f (dip-buy signal, no gates)",
            pair, side, rate,
        )
        return True
