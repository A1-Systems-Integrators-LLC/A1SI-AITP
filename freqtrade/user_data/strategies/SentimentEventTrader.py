"""SentimentEventTrader — News-driven sentiment strategy.

LEARNING PHASE: Conviction/risk gates DISABLED.

Trades sentiment signals from the NLP pipeline (FinBERT/VADER) via the backend API.
Long when aggregate sentiment is bullish + technical confirmation.
Technical fallback when sentiment is unavailable.
"""

import logging
import time

import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

logger = logging.getLogger(__name__)

LEARNING_PHASE = True

# Backend API for sentiment data (Docker internal network)
BACKEND_URL = "http://backend:8000"
_SENTIMENT_CACHE: dict[str, tuple[float, float]] = {}  # asset_class -> (score, timestamp)
_CACHE_TTL = 300  # 5 minutes


def _fetch_sentiment_signal(asset_class: str = "crypto") -> float:
    """Fetch aggregate sentiment signal from the backend API.

    Returns sentiment score [-1, 1] or 0.0 on failure.
    Caches results for 5 minutes to avoid hammering the API.
    """
    now = time.time()
    cached = _SENTIMENT_CACHE.get(asset_class)
    if cached and (now - cached[1]) < _CACHE_TTL:
        return cached[0]

    try:
        import requests

        resp = requests.get(
            f"{BACKEND_URL}/api/market/news/signal/",
            params={"asset_class": asset_class},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            score = float(data.get("signal", 0.0))
            _SENTIMENT_CACHE[asset_class] = (score, now)
            logger.info("Sentiment signal for %s: %.4f (%s)", asset_class, score, data.get("signal_label", "?"))
            return score
        # Auth required — try without auth (internal network)
        if resp.status_code in (401, 403):
            logger.debug("Sentiment API requires auth, using unauthenticated endpoint")
    except Exception as e:
        logger.warning("Sentiment API fetch failed: %s", e)

    _SENTIMENT_CACHE[asset_class] = (0.0, now)
    return 0.0


class SentimentEventTrader(IStrategy):
    """Trades sentiment signals with technical confirmation."""

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False  # Kraken spot only
    startup_candle_count = 50

    stoploss = -0.12
    use_custom_stoploss = True

    minimal_roi = {
        "0": 0.04,
        "60": 0.025,
        "240": 0.015,
        "480": 0.005,
    }

    # Sentiment thresholds — lowered for learning phase
    # Backend signal ranges [-1, 1], bullish threshold in signal.py is 0.15
    buy_sentiment_threshold = DecimalParameter(0.05, 0.5, default=0.10, space="buy")
    sell_sentiment_threshold = DecimalParameter(-0.5, -0.05, default=-0.10, space="sell")
    buy_rsi_max = IntParameter(55, 75, default=70, space="buy")
    sell_rsi_min = IntParameter(25, 45, default=35, space="sell")
    atr_multiplier = DecimalParameter(1.0, 3.0, default=2.0, space="buy")

    # Cached aggregate sentiment score (refreshed in bot_loop_start)
    _current_sentiment: float = 0.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["volume_sma"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_sma"]

        # Use the aggregate sentiment score from the backend API
        dataframe["sentiment_score"] = self._current_sentiment

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        sentiment = self._current_sentiment
        threshold = self.buy_sentiment_threshold.value

        # Path 1: Sentiment-driven entry — bullish sentiment + basic technical filter
        sentiment_entry = (
            (sentiment > threshold)
            & (dataframe["rsi"] < self.buy_rsi_max.value)
            & (dataframe["rsi"] > 25)
            & (dataframe["volume"] > 0)
        )

        # Path 2: Technical proxy — RSI oversold bounce + volume confirmation
        # Relaxed from original (RSI<35 + vol>1.3) to actually trigger in normal markets
        technical_entry = (
            (dataframe["rsi"] < 40)
            & (dataframe["rsi"].shift(1) < dataframe["rsi"])  # RSI turning up
            & (dataframe["volume_ratio"] > 1.1)  # Mild volume confirmation
            & (dataframe["close"] > dataframe["ema_50"])  # Above trend
        )

        # Path 3: Momentum entry — strong trend with sentiment not negative
        momentum_entry = (
            (sentiment >= 0)  # At least neutral sentiment
            & (dataframe["adx"] > 25)  # Trending market
            & (dataframe["ema_20"] > dataframe["ema_50"])  # Uptrend
            & (dataframe["close"] > dataframe["ema_20"])  # Price above fast EMA
            & (dataframe["rsi"] > 50) & (dataframe["rsi"] < 70)  # Not overbought
            & (dataframe["volume_ratio"] > 1.0)  # Normal+ volume
        )

        dataframe.loc[
            (sentiment_entry | technical_entry | momentum_entry),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (self._current_sentiment < self.sell_sentiment_threshold.value)
                | (dataframe["rsi"] > 75)
            ),
            "exit_long",
        ] = 1

        return dataframe

    def bot_loop_start(self, **kwargs) -> None:
        """Refresh aggregate sentiment score from backend API each tick."""
        self._current_sentiment = _fetch_sentiment_signal("crypto")

    def custom_leverage(self, pair: str, current_time, current_rate, proposed_leverage,
                        max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3.0, max_leverage)

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs) -> bool:
        logger.info(
            "ENTRY SIGNAL %s: %s @ %.6f (sentiment=%.4f, no gates)",
            pair, side, rate, self._current_sentiment,
        )
        return True

    def custom_stake_amount(self, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side,
                            **kwargs) -> float:
        return proposed_stake

    def custom_stoploss(self, pair, trade, current_time, current_rate,
                        current_profit, after_fill, **kwargs) -> float:
        atr = self.dp.get_pair_dataframe(pair, self.timeframe)["atr"].iloc[-1]
        atr_stop = (atr / current_rate) * self.atr_multiplier.value
        stop = -atr_stop

        if current_profit > 0.02:
            stop = max(stop, -0.025)
        if current_profit > 0.04:
            stop = max(stop, -0.015)

        return stop

    def custom_exit(self, pair, trade, current_time, current_rate,
                    current_profit, **kwargs):
        return None
