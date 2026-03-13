"""Signal Service — Django service layer wrapping the SignalAggregator.

Provides signal computation, batch processing, and entry recommendations
for API views and task executors.
"""

import logging
import threading
import time
from typing import Any

import pandas as pd

from core.platform_bridge import ensure_platform_imports

logger = logging.getLogger(__name__)

# Thread-safe signal cache with TTL
_signal_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_signal_cache_lock = threading.Lock()
SIGNAL_CACHE_TTL = 60  # seconds


def clear_signal_cache() -> None:
    """Clear the signal cache (for testing)."""
    with _signal_cache_lock:
        _signal_cache.clear()


class SignalService:
    """Django-side wrapper around common.signals.SignalAggregator.

    Collects live data from regime, ML, sentiment, and scanner sources,
    then feeds them into the aggregator for composite scoring.
    """

    @staticmethod
    def _get_aggregator():
        ensure_platform_imports()
        from common.signals.aggregator import SignalAggregator

        return SignalAggregator()

    @staticmethod
    def _get_regime_state(symbol: str, asset_class: str):
        """Fetch current regime state for a symbol."""
        try:
            ensure_platform_imports()
            from common.regime.regime_detector import RegimeDetector

            detector = RegimeDetector()
            return detector.detect(symbol, asset_class=asset_class)
        except Exception as e:
            logger.warning("Regime detection unavailable for %s: %s", symbol, e)
            return None

    @staticmethod
    def _get_ml_prediction(symbol: str, asset_class: str) -> tuple[float | None, float | None]:
        """Fetch ML prediction using ensemble (accuracy-weighted) with single-model fallback."""
        try:
            ensure_platform_imports()
            from common.data_pipeline.pipeline import load_ohlcv
            from common.ml.ensemble import ModelEnsemble
            from common.ml.features import build_feature_matrix

            df = load_ohlcv(symbol, "1h")
            if df is None or df.empty:
                logger.debug("No OHLCV data for ML prediction: %s", symbol)
                return None, None

            X, _y, _feature_names = build_feature_matrix(  # noqa: N806
                df,
                include_temporal=True,
                include_volatility_regime=True,
            )
            if X is None or X.empty:
                logger.debug("Empty feature matrix for ML prediction: %s", symbol)
                return None, None

            # Use only the latest row for prediction
            X_latest = X.tail(1)  # noqa: N806

            # Try ensemble first (accuracy-weighted, up to 5 models)
            ensemble = ModelEnsemble(mode="accuracy_weighted")
            n_models = ensemble.build_from_registry(
                asset_class=asset_class,
                symbol=symbol,
            )
            if n_models >= 2:
                result = ensemble.predict(X_latest)
                if result is not None:
                    # Use agreement_ratio as confidence proxy
                    confidence = result.agreement_ratio * (1.0 if n_models >= 3 else 0.8)
                    return result.probability, confidence

            # Fallback to single-model prediction
            from common.ml.prediction import PredictionService

            svc = PredictionService()
            result = svc.predict_single(symbol, X_latest, asset_class)
            if result is not None:
                return result.probability, result.confidence
        except Exception as e:
            logger.warning("ML prediction unavailable for %s: %s", symbol, e)
        return None, None

    @staticmethod
    def _get_sentiment_signal(symbol: str, asset_class: str) -> tuple[float | None, float | None]:
        """Fetch sentiment signal and conviction."""
        try:
            ensure_platform_imports()
            from common.sentiment.signal import compute_signal

            result = compute_signal(symbol, asset_class=asset_class)
            if result:
                return result.get("score", None), result.get("conviction", None)
        except Exception as e:
            logger.warning("Sentiment signal unavailable for %s: %s", symbol, e)
        return None, None

    @staticmethod
    def _get_scanner_score(symbol: str, asset_class: str) -> float | None:
        """Fetch latest scanner opportunity score."""
        try:
            from market.models import MarketOpportunity

            opp = (
                MarketOpportunity.objects.filter(
                    symbol=symbol,
                    asset_class=asset_class,
                    is_active=True,
                )
                .order_by("-detected_at")
                .first()
            )
            if opp:
                return opp.score
        except Exception as e:
            logger.warning("Scanner score unavailable for %s: %s", symbol, e)
        return None

    @staticmethod
    def _get_technical_score(symbol: str, asset_class: str, strategy_name: str) -> float | None:
        """Compute per-strategy technical score from latest OHLCV indicators."""
        try:
            ensure_platform_imports()
            from common.data_pipeline.pipeline import load_ohlcv
            from common.indicators.technical import (
                adx as compute_adx,
            )
            from common.indicators.technical import (
                bollinger_bands,
                ema,
                macd,
                stochastic,
            )
            from common.indicators.technical import (
                mfi as compute_mfi,
            )
            from common.indicators.technical import (
                rsi as compute_rsi,
            )
            from common.signals.technical_scorers import (
                SCORER_MAP,
                bmr_technical_score,
                civ1_technical_score,
                mean_reversion_technical_score,
                momentum_technical_score,
                vb_technical_score,
            )

            df = load_ohlcv(symbol, "1h", asset_class=asset_class)
            if df is None or len(df) < 100:
                return None

            # Compute common indicators on latest data
            close = df["close"]
            volume = df["volume"] if "volume" in df.columns else pd.Series(0, index=df.index)

            rsi_val = float(compute_rsi(close).iloc[-1])
            adx_val = float(compute_adx(df).iloc[-1])
            ema_21 = float(ema(close, 21).iloc[-1])
            ema_100 = float(ema(close, 100).iloc[-1])
            macd_df = macd(close)
            macd_hist_val = float(macd_df["macd_hist"].iloc[-1])
            vol_avg = (
                float(volume.rolling(20).mean().iloc[-1]) if float(volume.iloc[-1]) > 0 else 1.0
            )
            volume_ratio = float(volume.iloc[-1]) / vol_avg if vol_avg > 0 else 1.0
            close_val = float(close.iloc[-1])

            scorer_type = SCORER_MAP.get(strategy_name, "civ1")

            if scorer_type == "civ1":
                return civ1_technical_score(
                    rsi=rsi_val,
                    ema_short=ema_21,
                    ema_long=ema_100,
                    close=close_val,
                    macd_hist=macd_hist_val,
                    volume_ratio=volume_ratio,
                    adx_value=adx_val,
                )
            if scorer_type == "bmr":
                bb_df = bollinger_bands(close)
                bb_mid_val = float(bb_df["bb_mid"].iloc[-1])
                bb_w = float(bb_df["bb_width"].iloc[-1]) if "bb_width" in bb_df.columns else 0.0
                stoch_df = stochastic(df)
                mfi_val = float(compute_mfi(df).iloc[-1]) if float(volume.iloc[-1]) > 0 else 50.0
                return bmr_technical_score(
                    close=close_val,
                    bb_lower=float(bb_df["bb_lower"].iloc[-1]),
                    bb_mid=bb_mid_val,
                    bb_width=bb_w,
                    rsi=rsi_val,
                    stoch_k=float(stoch_df["stoch_k"].iloc[-1]),
                    mfi=mfi_val,
                    volume_ratio=volume_ratio,
                )
            if scorer_type == "vb":
                bb_df = bollinger_bands(close)
                bb_w = float(bb_df["bb_width"].iloc[-1]) if "bb_width" in bb_df.columns else 0.0
                bb_w_prev = (
                    float(bb_df["bb_width"].iloc[-2]) if "bb_width" in bb_df.columns else 0.0
                )
                high_20 = float(df["high"].rolling(20).max().iloc[-1])
                return vb_technical_score(
                    close=close_val,
                    high_n=high_20,
                    volume_ratio=volume_ratio,
                    bb_width=bb_w,
                    bb_width_prev=bb_w_prev,
                    adx_value=adx_val,
                    rsi=rsi_val,
                )
            if scorer_type == "momentum":
                return momentum_technical_score(
                    rsi=rsi_val,
                    ema_short=ema_21,
                    ema_long=ema_100,
                    close=close_val,
                    macd_hist=macd_hist_val,
                    adx_value=adx_val,
                    volume_ratio=volume_ratio,
                )
            if scorer_type == "mean_reversion":
                bb_df = bollinger_bands(close)
                bb_mid_val = float(bb_df["bb_mid"].iloc[-1])
                bb_w = float(bb_df["bb_width"].iloc[-1]) if "bb_width" in bb_df.columns else 0.0
                stoch_df = stochastic(df)
                mfi_val = float(compute_mfi(df).iloc[-1]) if float(volume.iloc[-1]) > 0 else 50.0
                return mean_reversion_technical_score(
                    close=close_val,
                    bb_lower=float(bb_df["bb_lower"].iloc[-1]),
                    bb_mid=bb_mid_val,
                    bb_width=bb_w,
                    rsi=rsi_val,
                    stoch_k=float(stoch_df["stoch_k"].iloc[-1]),
                    mfi=mfi_val,
                    volume_ratio=volume_ratio,
                )
        except Exception as e:
            logger.warning("Technical score unavailable for %s/%s: %s", symbol, strategy_name, e)
        return None

    @staticmethod
    def _get_win_rate(strategy_name: str) -> float | None:
        """Fetch historical win rate for a strategy from backtest results."""
        try:
            from analysis.models import BacktestResult

            recent = (
                BacktestResult.objects.filter(strategy_name=strategy_name)
                .order_by("-created_at")
                .first()
            )
            if recent and recent.metrics:
                wr = recent.metrics.get("win_rate")
                if wr is not None:
                    return float(wr)
        except Exception as e:
            logger.warning("Win rate unavailable for %s: %s", strategy_name, e)
        return None

    @classmethod
    def get_signal(
        cls,
        symbol: str,
        asset_class: str = "crypto",
        strategy_name: str = "CryptoInvestorV1",
    ) -> dict[str, Any]:
        """Compute composite signal for a symbol/strategy pair.

        Returns a dict with all signal components and the composite score.
        Uses a 60s TTL cache to avoid redundant computation.
        """
        cache_key = f"{symbol}:{asset_class}:{strategy_name}"
        now = time.monotonic()
        with _signal_cache_lock:
            cached = _signal_cache.get(cache_key)
            if cached and (now - cached[0]) < SIGNAL_CACHE_TTL:
                return cached[1]

        aggregator = cls._get_aggregator()

        regime_state = cls._get_regime_state(symbol, asset_class)
        technical = cls._get_technical_score(symbol, asset_class, strategy_name)
        ml_prob, ml_conf = cls._get_ml_prediction(symbol, asset_class)
        sent_score, sent_conv = cls._get_sentiment_signal(symbol, asset_class)
        scanner = cls._get_scanner_score(symbol, asset_class)
        win_rate = cls._get_win_rate(strategy_name)

        signal = aggregator.compute(
            symbol=symbol,
            asset_class=asset_class,
            strategy_name=strategy_name,
            technical_score=technical,
            regime_state=regime_state,
            ml_probability=ml_prob,
            ml_confidence=ml_conf,
            sentiment_signal=sent_score,
            sentiment_conviction=sent_conv,
            scanner_score=scanner,
            win_rate=win_rate,
        )

        result = {
            "symbol": signal.symbol,
            "asset_class": signal.asset_class,
            "timestamp": signal.timestamp.isoformat(),
            "composite_score": signal.composite_score,
            "signal_label": signal.signal_label,
            "entry_approved": signal.entry_approved,
            "position_modifier": signal.position_modifier,
            "hard_disabled": signal.hard_disabled,
            "components": {
                "technical": signal.technical_score,
                "regime": signal.regime_score,
                "ml": signal.ml_score,
                "sentiment": signal.sentiment_score,
                "scanner": signal.scanner_score,
                "win_rate": signal.screen_score,
            },
            "confidences": {
                "ml": signal.ml_confidence,
                "sentiment": signal.sentiment_conviction,
                "regime": signal.regime_confidence,
            },
            "sources_available": signal.sources_available,
            "reasoning": signal.reasoning,
        }
        with _signal_cache_lock:
            _signal_cache[cache_key] = (time.monotonic(), result)
        return result

    @classmethod
    def get_signals_batch(
        cls,
        symbols: list[str],
        asset_class: str = "crypto",
        strategy_name: str = "CryptoInvestorV1",
    ) -> list[dict[str, Any]]:
        """Compute signals for multiple symbols."""
        results = []
        for symbol in symbols[:50]:  # Cap at 50
            try:
                sig = cls.get_signal(symbol, asset_class, strategy_name)
                results.append(sig)
            except Exception as e:
                logger.warning("Signal computation failed for %s: %s", symbol, e)
                results.append(
                    {
                        "symbol": symbol,
                        "asset_class": asset_class,
                        "error": str(e),
                    }
                )
        return results

    @classmethod
    def get_entry_recommendation(
        cls,
        symbol: str,
        strategy_name: str,
        asset_class: str = "crypto",
    ) -> dict[str, Any]:
        """Get an entry gate recommendation for Freqtrade/NautilusTrader.

        Returns:
            dict with: approved (bool), score (float), position_modifier (float),
            reasoning (list[str])

        """
        signal = cls.get_signal(symbol, asset_class, strategy_name)
        return {
            "approved": signal["entry_approved"],
            "score": signal["composite_score"],
            "position_modifier": signal["position_modifier"],
            "reasoning": signal["reasoning"],
            "signal_label": signal["signal_label"],
            "hard_disabled": signal["hard_disabled"],
        }
