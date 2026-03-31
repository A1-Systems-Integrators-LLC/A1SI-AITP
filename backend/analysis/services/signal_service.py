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

# Thread-safe signal cache with regime-aware TTL
_signal_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_signal_cache_lock = threading.Lock()
_signal_cache_order: list[str] = []  # LRU order tracking
SIGNAL_CACHE_MAX_SIZE = 500

# Per-key computation locks: prevents multiple threads computing the same signal
# simultaneously, which causes threadpool exhaustion under Daphne.
_computation_locks: dict[str, threading.Lock] = {}
_computation_locks_lock = threading.Lock()
SIGNAL_COMPUTATION_TIMEOUT = 30  # seconds — fail-open if computation takes too long

# Regime-aware TTL mapping (seconds)
SIGNAL_CACHE_TTL_MAP = {
    "HIGH_VOLATILITY": 30,
    "STRONG_TREND_DOWN": 30,
    "STRONG_TREND_UP": 60,
    "WEAK_TREND_UP": 60,
    "WEAK_TREND_DOWN": 60,
    "RANGING": 120,
    "UNKNOWN": 60,
}
SIGNAL_CACHE_TTL_DEFAULT = 60  # seconds

# Cache statistics
_cache_hits = 0
_cache_misses = 0


def clear_signal_cache() -> None:
    """Clear the signal cache (for testing)."""
    global _cache_hits, _cache_misses
    with _signal_cache_lock:
        _signal_cache.clear()
        _signal_cache_order.clear()
        _cache_hits = 0
        _cache_misses = 0


def get_cache_stats() -> dict[str, int]:
    """Return cache hit/miss statistics."""
    return {"hits": _cache_hits, "misses": _cache_misses, "size": len(_signal_cache)}


def _get_cache_ttl(regime: str | None = None) -> int:
    """Get TTL based on current regime."""
    if regime:
        return SIGNAL_CACHE_TTL_MAP.get(regime, SIGNAL_CACHE_TTL_DEFAULT)
    return SIGNAL_CACHE_TTL_DEFAULT


def _evict_lru() -> None:
    """Evict least-recently-used entries when cache exceeds max size. Must hold lock."""
    while len(_signal_cache) > SIGNAL_CACHE_MAX_SIZE and _signal_cache_order:
        oldest_key = _signal_cache_order.pop(0)
        _signal_cache.pop(oldest_key, None)


class SignalService:
    """Django-side wrapper around common.signals.SignalAggregator.

    Collects live data from regime, ML, sentiment, and scanner sources,
    then feeds them into the aggregator for composite scoring.
    """

    _aggregator_instance = None
    _aggregator_lock = threading.Lock()

    @classmethod
    def _get_aggregator(cls):
        if cls._aggregator_instance is None:
            with cls._aggregator_lock:
                if cls._aggregator_instance is None:
                    ensure_platform_imports()
                    from common.signals.aggregator import SignalAggregator

                    cls._aggregator_instance = SignalAggregator()
        return cls._aggregator_instance

    @staticmethod
    def _get_regime_state(symbol: str, asset_class: str):
        """Fetch current regime state for a symbol."""
        try:
            ensure_platform_imports()
            from common.data_pipeline.pipeline import load_ohlcv
            from common.regime.regime_detector import RegimeDetector

            detector = RegimeDetector()
            exchange_id = "yfinance" if asset_class in ("equity", "forex") else "kraken"
            df = load_ohlcv(symbol, "1h", exchange_id)
            if df is None or df.empty:
                return None
            return detector.detect(df)
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
            from market.services.news import NewsService

            service = NewsService()
            signal_data = service.get_sentiment_signal(asset_class=asset_class, hours=24)
            if signal_data and signal_data.get("article_count", 0) > 0:
                return signal_data.get("signal"), signal_data.get("conviction")
        except Exception as e:
            logger.warning("Sentiment signal unavailable for %s: %s", symbol, e)
        return None, None

    @staticmethod
    def _get_scanner_score(symbol: str, asset_class: str) -> float | None:
        """Fetch latest scanner opportunity score."""
        try:
            from django.utils import timezone

            from market.models import MarketOpportunity

            now = timezone.now()
            opp = (
                MarketOpportunity.objects.filter(
                    symbol=symbol,
                    asset_class=asset_class,
                    expires_at__gt=now,
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

            source = "yfinance" if asset_class in ("equity", "forex") else "kraken"
            df = load_ohlcv(symbol, "1h", source)
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
                    bb_upper=float(bb_df["bb_upper"].iloc[-1]),
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
                    bb_upper=float(bb_df["bb_upper"].iloc[-1]),
                )
        except Exception as e:
            logger.warning("Technical score unavailable for %s/%s: %s", symbol, strategy_name, e)
        return None

    @staticmethod
    def _get_macro_score() -> float | None:
        """Fetch macro score from FRED adapter (VIX, yield curve, fed funds, DXY)."""
        try:
            ensure_platform_imports()
            from common.market_data.fred_adapter import fetch_macro_snapshot

            snapshot = fetch_macro_snapshot()
            return snapshot.get("macro_score") if snapshot else None
        except Exception as e:
            logger.warning("Macro score unavailable: %s", e)
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
        Uses a regime-aware TTL cache to avoid redundant computation.
        """
        global _cache_hits, _cache_misses
        cache_key = f"{symbol}:{asset_class}:{strategy_name}"
        now = time.monotonic()

        # Fast path: check cache without holding computation lock
        with _signal_cache_lock:
            cached = _signal_cache.get(cache_key)
            if cached:
                cached_regime = cached[1].get("_regime")
                ttl = _get_cache_ttl(cached_regime)
                if (now - cached[0]) < ttl:
                    _cache_hits += 1
                    if cache_key in _signal_cache_order:
                        _signal_cache_order.remove(cache_key)
                    _signal_cache_order.append(cache_key)
                    return cached[1]

        # Per-key lock: only one thread computes a given signal at a time.
        # Other threads for the same key wait for the result instead of
        # all running the heavy computation and exhausting the threadpool.
        with _computation_locks_lock:
            if cache_key not in _computation_locks:
                _computation_locks[cache_key] = threading.Lock()
            key_lock = _computation_locks[cache_key]

        if not key_lock.acquire(timeout=SIGNAL_COMPUTATION_TIMEOUT):
            # Another thread is computing this signal and timed out — fail open
            logger.warning("Signal computation timeout waiting for %s", cache_key)
            _cache_misses += 1
            return cls._fail_open_signal(symbol, asset_class)

        try:
            # Re-check cache — another thread may have populated it while we waited
            with _signal_cache_lock:
                cached = _signal_cache.get(cache_key)
                if cached:
                    cached_regime = cached[1].get("_regime")
                    ttl = _get_cache_ttl(cached_regime)
                    if (time.monotonic() - cached[0]) < ttl:
                        _cache_hits += 1
                        return cached[1]
                _cache_misses += 1

            aggregator = cls._get_aggregator()

            regime_state = cls._get_regime_state(symbol, asset_class)
            technical = cls._get_technical_score(symbol, asset_class, strategy_name)
            ml_prob, ml_conf = cls._get_ml_prediction(symbol, asset_class)
            sent_score, sent_conv = cls._get_sentiment_signal(symbol, asset_class)
            scanner = cls._get_scanner_score(symbol, asset_class)
            win_rate = cls._get_win_rate(strategy_name)
            macro = cls._get_macro_score()

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
                macro_score=macro,
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
            regime_name = regime_state.regime.value if regime_state else None
            result["_regime"] = regime_name
            with _signal_cache_lock:
                _signal_cache[cache_key] = (time.monotonic(), result)
                if cache_key in _signal_cache_order:
                    _signal_cache_order.remove(cache_key)
                _signal_cache_order.append(cache_key)
                _evict_lru()
            return result
        finally:
            key_lock.release()

    @staticmethod
    def _fail_open_signal(symbol: str, asset_class: str) -> dict[str, Any]:
        """Return a neutral signal when computation times out (fail-open)."""
        from datetime import datetime, timezone

        return {
            "symbol": symbol,
            "asset_class": asset_class,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "composite_score": 0.0,
            "signal_label": "neutral",
            "entry_approved": True,
            "position_modifier": 1.0,
            "hard_disabled": False,
            "components": {},
            "confidences": {},
            "sources_available": 0,
            "reasoning": ["Signal computation timed out — fail-open"],
            "_regime": None,
        }

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

    @staticmethod
    def get_pipeline_health(asset_class: str = "crypto") -> dict:
        """Check health of each signal source in the pipeline."""
        import time

        from django.utils import timezone as tz

        sources: dict[str, Any] = {}
        now = tz.now()

        # Technical scorer
        t0 = time.monotonic()
        try:
            ensure_platform_imports()
            from common.indicators.technical import add_all_indicators  # noqa: F401
            sources["technical"] = {"status": "ok", "latency_ms": 0}
        except Exception as e:
            sources["technical"] = {"status": "error", "error": str(e)}
        sources["technical"]["latency_ms"] = round((time.monotonic() - t0) * 1000)

        # Regime detector
        t0 = time.monotonic()
        try:
            ensure_platform_imports()
            from common.regime.regime_detector import RegimeDetector  # noqa: F401
            sources["regime"] = {"status": "ok", "latency_ms": 0}
        except Exception as e:
            sources["regime"] = {"status": "error", "error": str(e)}
        sources["regime"]["latency_ms"] = round((time.monotonic() - t0) * 1000)

        # ML prediction
        t0 = time.monotonic()
        try:
            ensure_platform_imports()
            from common.ml.prediction import PredictionService  # noqa: F401
            from common.ml.registry import ModelRegistry
            models = ModelRegistry().list_models()
            sources["ml"] = {
                "status": "ok" if models else "unavailable",
                "model_count": len(models),
                "latency_ms": 0,
            }
        except Exception as e:
            sources["ml"] = {"status": "error", "error": str(e)}
        sources["ml"]["latency_ms"] = round((time.monotonic() - t0) * 1000)

        # Sentiment/News
        t0 = time.monotonic()
        try:
            from market.models import NewsArticle
            recent_count = NewsArticle.objects.filter(
                published_at__gte=now - tz.timedelta(hours=24),
            ).count()
            sources["sentiment"] = {
                "status": "ok" if recent_count > 0 else "stale",
                "articles_24h": recent_count,
                "latency_ms": 0,
            }
        except Exception as e:
            sources["sentiment"] = {"status": "error", "error": str(e)}
        sources["sentiment"]["latency_ms"] = round((time.monotonic() - t0) * 1000)

        # Scanner
        t0 = time.monotonic()
        try:
            from market.models import MarketOpportunity
            active_opps = MarketOpportunity.objects.filter(
                asset_class=asset_class,
                expires_at__gt=now,
            ).count()
            sources["scanner"] = {
                "status": "ok",
                "active_opportunities": active_opps,
                "latency_ms": 0,
            }
        except Exception as e:
            sources["scanner"] = {"status": "error", "error": str(e)}
        sources["scanner"]["latency_ms"] = round((time.monotonic() - t0) * 1000)

        # Win rate
        t0 = time.monotonic()
        try:
            from trading.models import Order
            filled_count = Order.objects.filter(status="FILLED").count()
            sources["win_rate"] = {
                "status": "ok" if filled_count >= 20 else "insufficient_data",
                "filled_orders": filled_count,
                "latency_ms": 0,
            }
        except Exception as e:
            sources["win_rate"] = {"status": "error", "error": str(e)}
        sources["win_rate"]["latency_ms"] = round((time.monotonic() - t0) * 1000)

        # Funding (crypto only)
        t0 = time.monotonic()
        if asset_class == "crypto":
            try:
                ensure_platform_imports()
                from common.data_pipeline.pipeline import load_funding_rates
                fr = load_funding_rates("BTC/USDT")
                sources["funding"] = {
                    "status": "ok" if fr is not None and not fr.empty else "no_data",
                    "latency_ms": 0,
                }
            except Exception as e:
                sources["funding"] = {"status": "error", "error": str(e)}
            sources["funding"]["latency_ms"] = round((time.monotonic() - t0) * 1000)
        else:
            sources["funding"] = {
                "status": "n/a",
                "reason": f"Not applicable for {asset_class}",
            }

        # Macro
        t0 = time.monotonic()
        try:
            ensure_platform_imports()
            from common.market_data.fred_adapter import fetch_macro_snapshot
            snapshot = fetch_macro_snapshot()
            sources["macro"] = {
                "status": "ok" if snapshot else "no_data",
                "latency_ms": 0,
            }
        except Exception as e:
            sources["macro"] = {"status": "unavailable", "error": str(e)}
        sources["macro"]["latency_ms"] = round((time.monotonic() - t0) * 1000)

        # Overall health
        ok_count = sum(1 for s in sources.values() if s.get("status") == "ok")
        total = len(sources)

        return {
            "asset_class": asset_class,
            "timestamp": now.isoformat(),
            "overall_status": "healthy" if ok_count >= total * 0.6 else "degraded",
            "sources_ok": ok_count,
            "sources_total": total,
            "sources": sources,
        }
