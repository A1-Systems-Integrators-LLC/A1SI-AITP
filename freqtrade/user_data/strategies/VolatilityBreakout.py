"""VolatilityBreakout — Freqtrade Strategy
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
        - ADX 15-45 rising (emerging-to-moderate trend)
        - RSI 30-70 (recovering from oversold or neutral — fresh move)

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
from datetime import datetime

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
        "0": 0.05,     # 5% ROI target (take profits faster)
        "60": 0.03,    # 3% after 1 hour
        "180": 0.02,   # 2% after 3 hours
        "360": 0.005,  # 0.5% after 6 hours
    }

    stoploss = -0.05  # -5% hard stop (give breakouts room to develop)
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

    # Hyperopt parameters — aggressive defaults for high trade frequency
    breakout_period = IntParameter(10, 30, default=20, space="buy", optimize=True)
    volume_factor = DecimalParameter(0.8, 3.0, default=1.2, decimals=1, space="buy", optimize=True)
    adx_low = IntParameter(5, 30, default=15, space="buy", optimize=True)
    adx_high = IntParameter(25, 65, default=55, space="buy", optimize=True)
    rsi_low = IntParameter(20, 40, default=25, space="buy", optimize=True)
    rsi_high = IntParameter(65, 80, default=75, space="buy", optimize=True)
    sell_rsi_threshold = IntParameter(75, 95, default=80, space="sell", optimize=True)
    adx_tolerance = DecimalParameter(0.0, 3.0, default=2.0, decimals=1, space="buy", optimize=True)
    atr_multiplier = DecimalParameter(1.0, 3.5, default=2.0, decimals=1, space="buy", optimize=True)

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
        """Aggressive breakout entries: price breaks N-period high + volume OR price above EMA20.

        BB width expansion and ADX rising removed as hard requirements.
        """
        # Required: breakout above N-period high
        breakout = dataframe["close"] > dataframe[f"high_{self.breakout_period.value}"].shift(1)

        # Required: volume confirms the breakout (no weak alternatives)
        vol_confirm = dataframe["volume_ratio"] > float(self.volume_factor.value)

        # ADX in acceptable range with rising requirement (momentum building)
        adx_ok = (
            (dataframe["adx"] >= self.adx_low.value)
            & (dataframe["adx"] <= self.adx_high.value)
            & (dataframe["adx"] > dataframe["adx_prev"])  # ADX rising
        )

        # RSI in acceptable range (wide: 25-75 default)
        rsi_ok = (dataframe["rsi"] >= self.rsi_low.value) & (dataframe["rsi"] <= self.rsi_high.value)

        # Volume present
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
            logger.info(f"Stake adjusted {pair}: {proposed_stake:.2f} × {modifier:.2f} = {result:.2f}")
        return result

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
        """Conviction-based exit: regime deterioration, time limits."""
        return check_exit_advice(self, pair, trade, current_time, current_profit)

    def custom_stoploss(
        self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs,
    ):
        """ATR-based dynamic stop loss with regime-aware tightening."""
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

        # Tighten as profit increases (breakouts: protect gains quickly)
        if current_profit > 0.07:
            atr_stop = max(atr_stop, -0.025)  # Tight at 7%+
        elif current_profit > 0.04:
            atr_stop = max(atr_stop, -0.035)  # Moderate at 4%+

        return max(atr_stop, self.stoploss)
