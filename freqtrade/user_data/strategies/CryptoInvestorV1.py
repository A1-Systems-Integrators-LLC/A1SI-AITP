"""CryptoInvestorStrategy v1 — Freqtrade Strategy
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
from datetime import datetime, timedelta
from functools import reduce

import talib.abstract as ta
from _conviction_helpers import (
    check_conviction,
    check_exit_advice,
    get_position_modifier,
    get_regime_stop_multiplier,
    record_entry_regime,
    refresh_signals,
)
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
    IStrategy,
)
from pandas import DataFrame

logger = logging.getLogger(__name__)


class CryptoInvestorV1(IStrategy):
    """Trend-following strategy with RSI pullback entries.

    Designed for spot crypto trading on 1h timeframe.
    """

    # ── Strategy metadata ──
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    # Warm-up: need at least buy_ema_slow (100) candles for indicators to be valid.
    startup_candle_count = 150

    # ── Risk API integration ──
    risk_api_url = "http://127.0.0.1:8000"
    risk_portfolio_id = 1

    # ── ROI table (aggressive: take profits faster) ──
    minimal_roi = {
        "0": 0.05,     # 5% ROI target
        "60": 0.03,    # 3% after 1 hour
        "240": 0.02,   # 2% after 4 hours
        "720": 0.005,  # 0.5% after 12 hours
    }

    # ── Stop loss ──
    stoploss = -0.07  # -7% hard stop loss (ATR-based custom stop is primary)
    use_custom_stoploss = True

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
    # Pilot-tuned: relaxed from 50/200/40 to generate trades in sideways markets.
    # Run hyperopt (--epochs 200) on recent kraken data to further optimize.
    buy_ema_fast = IntParameter(10, 80, default=21, space="buy", optimize=True)
    buy_ema_slow = IntParameter(50, 300, default=100, space="buy", optimize=True)
    buy_rsi_threshold = IntParameter(25, 55, default=45, space="buy", optimize=True)
    sell_rsi_threshold = IntParameter(65, 90, default=75, space="sell", optimize=True)
    atr_multiplier = DecimalParameter(1.5, 4.0, default=2.5, decimals=1, space="buy", optimize=True)

    # ── Informative pairs ──
    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """Dynamic leverage: base 3x, scaled by conviction modifier, capped at 5x."""
        modifier = get_position_modifier(self, pair)
        lev = min(3.0 * modifier, 5.0)
        return min(lev, max_leverage)

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
        """Define entry (buy) conditions.

        Aggressive mode: RSI pullback + any ONE confirmation signal.
        EMA alignment removed — trades in any trend direction.
        """
        # Required: RSI pullback (core signal)
        rsi_pullback = dataframe["rsi"] < self.buy_rsi_threshold.value

        # Required: minimal trend filter — EMA-21 above EMA-50 OR EMA-50 rising
        # Prevents counter-trend entries in WEAK_TREND_DOWN
        ema_fast = f"ema_{self.buy_ema_fast.value}"
        ema_slow = f"ema_{self.buy_ema_slow.value}"
        ema_directional = (
            (dataframe[ema_fast] > dataframe[ema_slow])
            | (dataframe[ema_slow] > dataframe[ema_slow].shift(5))
        )

        # Confirmation signals — need at least ONE
        macd_improving = (
            (dataframe["macdhist"] > dataframe["macdhist"].shift(1))
            | (dataframe["macd"] > dataframe["macdsignal"])
        )
        volume_spike = dataframe["volume_ratio"] > 1.0

        any_confirmation = macd_improving | volume_spike

        # Basic filters
        has_volume = dataframe["volume"] > 0
        not_overbought = dataframe["rsi"] > 10  # not in freefall

        dataframe.loc[
            rsi_pullback & ema_directional & any_confirmation & has_volume & not_overbought,
            "enter_long",
        ] = 1

        # ── Short entry: EMA bearish alignment + RSI overbought + MACD declining ──
        ema_bearish = (
            (dataframe[ema_fast] < dataframe[ema_slow])
            | (dataframe[ema_slow] < dataframe[ema_slow].shift(5))
        )
        rsi_overbought = dataframe["rsi"] > 60
        macd_declining = (
            (dataframe["macdhist"] < dataframe["macdhist"].shift(1))
            | (dataframe["macd"] < dataframe["macdsignal"])
        )
        not_oversold = dataframe["rsi"] < 90

        dataframe.loc[
            ema_bearish & rsi_overbought & macd_declining & has_volume & not_oversold,
            "enter_short",
        ] = 1

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

        # ── Short exit: RSI oversold OR price crosses above fast EMA ──
        exit_short_rsi = dataframe["rsi"] < 30
        exit_short_trend = (
            (dataframe["close"] > dataframe[f"ema_{self.buy_ema_fast.value}"])
            & (dataframe["close"].shift(1) <= dataframe[f"ema_{self.buy_ema_fast.value}"].shift(1))
        )

        dataframe.loc[exit_short_rsi | exit_short_trend, "exit_short"] = 1

        return dataframe

    def bot_loop_start(self, current_time=None, **kwargs) -> None:
        """Fetch and cache composite signals for all active pairs (every 5 min)."""
        refresh_signals(self)

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
        """Scale position size by conviction score modifier."""
        from freqtrade.enums import RunMode

        if self.dp and self.dp.runmode in (RunMode.BACKTEST, RunMode.HYPEROPT):
            return proposed_stake

        modifier = get_position_modifier(self, pair)
        adjusted = proposed_stake * modifier
        effective_min = min_stake if min_stake is not None else 0.0
        result = max(min(adjusted, max_stake), effective_min)
        if modifier != 1.0:
            logger.info(
                "Stake adjusted %s: %.2f × %.2f = %.2f",
                pair, proposed_stake, modifier, result,
            )
        return result

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
        """ATR-based dynamic stop loss with regime-aware tightening.

        - Initial: 2x ATR below entry
        - Tightens as profit increases
        - Further tightened in unfavorable regimes
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        if dataframe.empty:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr = last_candle.get("atr", 0)

        if atr == 0:
            return self.stoploss

        # Regime-aware stop multiplier (0.5 in STRONG_TREND_DOWN, 1.0 in STRONG_TREND_UP)
        regime_mult = get_regime_stop_multiplier(self, pair)

        # ATR-based stop distance, tightened by regime
        atr_stop = -(atr * float(self.atr_multiplier.value) * regime_mult) / current_rate

        # Tighten stop as profit increases
        if current_profit > 0.08:
            atr_stop = max(atr_stop, -0.03)  # Tighten to -3%
        elif current_profit > 0.05:
            atr_stop = max(atr_stop, -0.04)  # Tighten to -4%

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
    ) -> str | None:
        """Custom exit logic: conviction advisor + trend/stale checks."""
        # 1. Conviction-based exit (regime deterioration, time limits)
        exit_tag = check_exit_advice(self, pair, trade, current_time, current_profit)
        if exit_tag:
            return exit_tag

        # 2. Technical exit checks
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
        if trade.open_date_utc + timedelta(days=7) < current_time and current_profit < 0.01:
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
        """Gate trades through risk API + conviction system (fail-open).

        In backtesting/hyperopt mode, skip API calls since the backend
        may not be running and checks are not meaningful for historical sims.
        """
        from freqtrade.enums import RunMode

        if self.dp and self.dp.runmode in (RunMode.BACKTEST, RunMode.HYPEROPT):
            return True

        # 1. Risk gate (existing)
        try:
            import requests

            stop_loss_price = rate * (1 + self.stoploss)  # stoploss is negative
            resp = requests.post(
                f"{self.risk_api_url}/api/risk/{self.risk_portfolio_id}/check-trade/",
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
            else:
                logger.warning(f"Risk API returned {resp.status_code}, approving (fail-open)")
        except Exception as e:
            logger.warning(f"Risk API unreachable ({e}), approving (fail-open)")

        # 2. Conviction gate
        if not check_conviction(self, pair):
            return False

        # Record entry regime for exit advisor
        record_entry_regime(self, pair)

        return True
