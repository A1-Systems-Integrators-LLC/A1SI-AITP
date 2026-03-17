"""SentimentEventTrader — News-driven extreme sentiment strategy.

Trades extreme sentiment spikes detected by the NLP pipeline (FinBERT/VADER).
Long on sentiment > 0.7, short on sentiment < -0.7.
Gate: RSI must not already be extended in the direction of the trade.
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

# Sentiment signal access
try:
    import importlib

    HAS_SENTIMENT = (
        importlib.util.find_spec("common.sentiment.scorer") is not None
        and importlib.util.find_spec("common.sentiment.signal") is not None
    )
except Exception:
    HAS_SENTIMENT = False


class SentimentEventTrader(IStrategy):
    """Trades extreme sentiment events from NLP pipeline."""

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    startup_candle_count = 50

    stoploss = -0.05
    use_custom_stoploss = True

    minimal_roi = {
        "0": 0.04,
        "60": 0.025,
        "240": 0.015,
        "480": 0.005,
    }

    # Hyperopt parameters
    buy_sentiment_threshold = DecimalParameter(0.5, 0.9, default=0.7, space="buy")
    sell_sentiment_threshold = DecimalParameter(-0.9, -0.5, default=-0.7, space="sell")
    buy_rsi_max = IntParameter(55, 75, default=65, space="buy")
    sell_rsi_min = IntParameter(25, 45, default=35, space="sell")
    atr_multiplier = DecimalParameter(1.0, 3.0, default=2.0, space="buy")

    # Cached sentiment scores per pair
    _sentiment_scores: dict[str, float] = {}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["volume_sma"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_sma"]

        # Add sentiment score column from cached values
        pair = metadata.get("pair", "")
        sentiment = self._sentiment_scores.get(pair, 0.0)
        dataframe["sentiment_score"] = sentiment

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long: extreme positive sentiment + RSI not overbought
        dataframe.loc[
            (
                (dataframe["sentiment_score"] > self.buy_sentiment_threshold.value)
                & (dataframe["rsi"] < self.buy_rsi_max.value)
                & (dataframe["rsi"] > 20)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        # Short: extreme negative sentiment + RSI not oversold
        dataframe.loc[
            (
                (dataframe["sentiment_score"] < self.sell_sentiment_threshold.value)
                & (dataframe["rsi"] > self.sell_rsi_min.value)
                & (dataframe["rsi"] < 80)
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit long: sentiment reverses or RSI overbought
        dataframe.loc[
            (
                (dataframe["sentiment_score"] < 0)
                | (dataframe["rsi"] > 75)
            ),
            "exit_long",
        ] = 1

        # Exit short: sentiment reverses or RSI oversold
        dataframe.loc[
            (
                (dataframe["sentiment_score"] > 0)
                | (dataframe["rsi"] < 25)
            ),
            "exit_short",
        ] = 1

        return dataframe

    def bot_loop_start(self, **kwargs) -> None:
        if HAS_CONVICTION:
            refresh_signals(self)

        # Refresh sentiment scores for active pairs
        if HAS_SENTIMENT and hasattr(self, "dp") and self.dp is not None:
            try:
                pairs = self.dp.current_whitelist()
                for pair in pairs[:10]:
                    signal = self._get_cached_signal(pair)
                    if signal is not None:
                        self._sentiment_scores[pair] = signal.get("sentiment_score", 0.0)
            except Exception as e:
                logger.warning("Sentiment refresh failed: %s", e)

    def _get_cached_signal(self, pair: str) -> dict | None:
        """Get cached conviction signal with sentiment data."""
        if not HAS_CONVICTION:
            return None
        signals = getattr(self, "_signals", {})
        return signals.get(pair)

    def custom_leverage(self, pair: str, current_time, current_rate, proposed_leverage,
                        max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3.0, max_leverage)

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

        if current_profit > 0.02:
            stop = max(stop, -0.025)
        if current_profit > 0.04:
            stop = max(stop, -0.015)

        return stop

    def custom_exit(self, pair, trade, current_time, current_rate,
                    current_profit, **kwargs):
        if HAS_CONVICTION:
            advice = check_exit_advice(self, pair, trade, current_time, current_profit)
            if advice:
                return advice
        return None
