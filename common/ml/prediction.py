"""ML Prediction Service
=====================
Real-time prediction with model selection cascade, caching, and batch support.
Integrates with ModelRegistry and SignalAggregator.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from common.ml.registry import ModelRegistry

logger = logging.getLogger(__name__)

try:
    import lightgbm as lgb

    HAS_LIGHTGBM = True
except ImportError:  # pragma: no cover
    HAS_LIGHTGBM = False
    lgb = None  # type: ignore[assignment]


@dataclass
class PredictionResult:
    """Result from a single ML prediction."""

    symbol: str
    probability: float  # calibrated probability (0.0-1.0)
    raw_probability: float  # uncalibrated model output
    confidence: float  # 0.0-1.0
    direction: str  # "up" or "down"
    model_id: str
    regime: str = ""
    asset_class: str = "crypto"
    predicted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PredictionService:
    """Real-time ML prediction service with model selection and caching.

    Model selection cascade:
    1. Exact symbol match (e.g., model trained on BTC/USDT)
    2. Asset-class match (best accuracy model for crypto/equity/forex)
    3. Best-accuracy fallback (any model, highest accuracy)
    """

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        cache_ttl: float = 300.0,
        calibrator: object | None = None,
    ):
        self._registry = registry or ModelRegistry()
        self._cache_ttl = cache_ttl
        self._calibrator = calibrator
        self._cache: dict[str, tuple[float, PredictionResult]] = {}
        self._lock = threading.Lock()

    def predict_single(
        self,
        symbol: str,
        features: pd.DataFrame,
        asset_class: str = "crypto",
        regime: str = "",
    ) -> PredictionResult | None:
        """Generate prediction for a single symbol.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT").
            features: Feature matrix (single row or multi-row, last row used).
            asset_class: Asset class for model selection.
            regime: Current regime label (for metadata).

        Returns:
            PredictionResult or None if no model available.

        """
        # Check cache
        cache_key = f"{symbol}:{asset_class}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Select model
        model_id = self._select_model(symbol, asset_class)
        if model_id is None:
            logger.debug("No model available for %s (%s)", symbol, asset_class)
            return None

        try:
            model, manifest = self._registry.load_model(model_id)
        except (FileNotFoundError, ImportError) as e:
            logger.warning("Failed to load model %s: %s", model_id, e)
            return None

        # Run inference
        try:
            if HAS_LIGHTGBM and isinstance(model, lgb.Booster):
                raw_proba = model.predict(features)
                if isinstance(raw_proba, np.ndarray) and raw_proba.ndim == 1:
                    raw_prob = float(raw_proba[-1])
                else:
                    raw_prob = float(np.array(raw_proba).flat[-1])
            else:
                proba = model.predict_proba(features)  # type: ignore[union-attr]
                raw_prob = float(proba[-1, 1]) if proba.ndim == 2 else float(proba[-1])
        except Exception as e:
            logger.warning("Prediction failed for %s: %s", symbol, e)
            return None

        # Calibrate — use explicit calibrator or load from model metadata
        calibrated_prob = raw_prob
        if self._calibrator is not None:
            try:
                calibrated_prob = self._calibrator.calibrate(raw_prob)  # type: ignore[union-attr]
            except Exception:
                calibrated_prob = raw_prob
        else:
            # Auto-load calibration from model metadata if available
            cal_params = manifest.get("metadata", {}).get("calibration")
            if cal_params and "a" in cal_params and "b" in cal_params:
                try:
                    import math

                    a, b = cal_params["a"], cal_params["b"]
                    calibrated_prob = 1.0 / (1.0 + math.exp(a * raw_prob + b))
                except Exception:
                    calibrated_prob = raw_prob

        # Compute confidence
        accuracy = manifest.get("metrics", {}).get("accuracy", 0.5)
        confidence = abs(calibrated_prob - 0.5) * 2 * accuracy

        direction = "up" if calibrated_prob >= 0.5 else "down"

        result = PredictionResult(
            symbol=symbol,
            probability=round(calibrated_prob, 4),
            raw_probability=round(raw_prob, 4),
            confidence=round(min(confidence, 1.0), 4),
            direction=direction,
            model_id=model_id,
            regime=regime,
            asset_class=asset_class,
        )

        # Cache result
        self._set_cached(cache_key, result)
        return result

    def predict_batch(
        self,
        symbols: list[str],
        features_map: dict[str, pd.DataFrame],
        asset_class: str = "crypto",
        regime: str = "",
    ) -> list[PredictionResult]:
        """Generate predictions for multiple symbols.

        Args:
            symbols: List of trading symbols.
            features_map: Dict mapping symbol → feature DataFrame.
            asset_class: Asset class for model selection.
            regime: Current regime label.

        Returns:
            List of PredictionResult (only successful predictions).

        """
        results = []
        for sym in symbols:
            feat = features_map.get(sym)
            if feat is None or feat.empty:
                continue
            result = self.predict_single(sym, feat, asset_class, regime)
            if result is not None:
                results.append(result)
        return results

    def score_opportunity(
        self,
        symbol: str,
        features: pd.DataFrame,
        opp_type: str,
        scanner_score: float,
        asset_class: str = "crypto",
    ) -> float:
        """Blend ML prediction with scanner score for opportunity ranking.

        Args:
            symbol: Trading symbol.
            features: Feature matrix.
            opp_type: Scanner opportunity type (e.g., "breakout").
            scanner_score: Raw scanner score (0-100).
            asset_class: Asset class.

        Returns:
            Blended score (0-100). Returns scanner_score if ML unavailable.

        """
        prediction = self.predict_single(symbol, features, asset_class)
        if prediction is None:
            return scanner_score

        ml_score = prediction.probability * 100
        ml_weight = min(prediction.confidence, 0.5)  # Cap ML influence at 50%
        blended = ml_score * ml_weight + scanner_score * (1 - ml_weight)
        return round(min(max(blended, 0.0), 100.0), 2)

    def invalidate_cache(self, symbol: str | None = None) -> None:
        """Clear prediction cache."""
        with self._lock:
            if symbol is None:
                self._cache.clear()
            else:
                keys_to_remove = [k for k in self._cache if k.startswith(f"{symbol}:")]
                for k in keys_to_remove:
                    del self._cache[k]

    def _select_model(self, symbol: str, asset_class: str) -> str | None:
        """Select best model using cascade: exact symbol → asset class → best accuracy."""
        models = self._registry.list_models()
        if not models:
            return None

        # 1. Exact symbol match (most recent)
        for m in models:
            if m.get("symbol", "").replace("/", "") == symbol.replace("/", ""):
                return m["model_id"]

        # 2. Asset-class match by label
        asset_models = [
            m for m in models if asset_class.lower() in (m.get("label", "") or "").lower()
        ]
        if asset_models:
            best = max(asset_models, key=lambda m: m.get("metrics", {}).get("accuracy", 0))
            return best["model_id"]

        # 3. Best accuracy fallback
        best = max(models, key=lambda m: m.get("metrics", {}).get("accuracy", 0))
        return best["model_id"]

    def _get_cached(self, key: str) -> PredictionResult | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ts, result = entry
            if time.monotonic() - ts > self._cache_ttl:
                del self._cache[key]
                return None
            return result

    def _set_cached(self, key: str, result: PredictionResult) -> None:
        with self._lock:
            self._cache[key] = (time.monotonic(), result)
