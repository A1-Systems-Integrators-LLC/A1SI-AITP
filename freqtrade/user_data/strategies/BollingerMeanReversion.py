"""BollingerMeanReversion — Freqtrade Strategy
=============================================
Mean-reversion strategy using Bollinger Bands with volume and RSI confirmation.

Logic:
    ENTRY (Long):
        - Price closes below lower Bollinger Band (2 std dev)
        - RSI < 35 (oversold confirmation)
        - Volume spike (volume > 1.5x 20-period average)
        - ADX < 50 (allows oversold bounces in moderate-to-strong trends)
        - Tighter stoploss when ADX > 35 (risk-adjusted for trend strength)

    EXIT:
        - Price reaches Bollinger middle band (SMA 20)
        - RSI > 65
        - Tiered ROI

Best suited for ranging/consolidating markets, but also catches oversold
bounces in downtrends with tighter risk management.
"""

import logging
from datetime import datetime
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


class BollingerMeanReversion(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    # Warm-up: BB period up to 30, plus RSI/ADX/ATR 14 — need at least 30 candles.
    startup_candle_count = 50

    # ── Risk API integration ──
    risk_api_url = "http://127.0.0.1:8000"
    risk_portfolio_id = 1

    minimal_roi = {
        "0": 0.04,     # 4% ROI target (take profits faster)
        "60": 0.025,   # 2.5% after 1 hour
        "240": 0.015,  # 1.5% after 4 hours
        "480": 0.005,  # 0.5% after 8 hours
    }

    stoploss = -0.06
    use_custom_stoploss = True
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

    # Hyperopt parameters — aggressive defaults for high trade frequency
    buy_bb_period = IntParameter(15, 30, default=20, space="buy", optimize=True)
    buy_bb_std = DecimalParameter(0.8, 3.0, default=1.5, decimals=1, space="buy", optimize=True)
    buy_rsi_threshold = IntParameter(25, 50, default=40, space="buy", optimize=True)
    buy_volume_factor = DecimalParameter(
        0.0, 2.5, default=0.5, decimals=1, space="buy", optimize=True,
    )
    buy_adx_ceiling = IntParameter(25, 60, default=40, space="buy", optimize=True)
    sell_rsi_threshold = IntParameter(55, 75, default=60, space="sell", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        from freqtrade.enums import RunMode

        # Full BB grid only needed for hyperopt optimization
        if self.dp and self.dp.runmode == RunMode.HYPEROPT:
            for period in [15, 20, 25, 30]:
                for std in [1.0, 1.2, 1.5, 2.0, 2.5, 3.0]:
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
        """Aggressive mean-reversion entries: price near lower BB + RSI oversold.

        Volume factor defaults to 0.0 (disabled) for maximum trade frequency.
        """
        std_str = str(float(self.buy_bb_std.value)).replace(".", "")
        bb_suffix = f"_{self.buy_bb_period.value}_{std_str}"

        conditions = [
            # Price below or near lower Bollinger Band
            dataframe["close"] < dataframe[f"bb_lower{bb_suffix}"],

            # RSI oversold
            dataframe["rsi"] < self.buy_rsi_threshold.value,

            # ADX ceiling — allow entry in moderate-to-strong trends
            dataframe["adx"] < self.buy_adx_ceiling.value,

            # Not in extreme downtrend (some floor)
            dataframe["rsi"] > 10,

            # Volume present
            dataframe["volume"] > 0,
        ]

        # Volume spike is optional (only apply if factor > 0)
        vol_factor = float(self.buy_volume_factor.value)
        if vol_factor > 0:
            conditions.append(dataframe["volume_ratio"] > vol_factor)

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
        self, pair, trade, current_time, current_rate,
        current_profit, after_fill, **kwargs,
    ):
        """ATR-based dynamic stop loss with regime-aware tightening."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr = last_candle.get("atr", 0)
        adx = last_candle.get("adx", 0)
        if atr == 0:
            return self.stoploss

        # Regime-aware stop multiplier (0.5 in STRONG_TREND_DOWN, 1.0 in STRONG_TREND_UP)
        regime_mult = get_regime_stop_multiplier(self, pair)

        # Tighter stop in strong trends (ADX > 35) — mean reversion is riskier
        atr_mult = 1.5 if adx > 35 else 2.0
        atr_stop = -(atr * atr_mult * regime_mult) / current_rate

        if current_profit > 0.04:
            atr_stop = max(atr_stop, -0.025)
        elif current_profit > 0.02:
            atr_stop = max(atr_stop, -0.03)

        return max(atr_stop, self.stoploss)
