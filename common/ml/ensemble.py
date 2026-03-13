"""
ML Model Ensemble
=================
Multi-model ensemble with 3 aggregation modes.
Combines predictions from multiple models for more robust signals.
"""

import logging
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

MAX_ENSEMBLE_SIZE = 5


@dataclass
class EnsembleResult:
    """Result from an ensemble prediction."""

    probability: float  # aggregated probability (0.0-1.0)
    direction: str  # "up" or "down"
    agreement_ratio: float  # fraction of models agreeing on direction (0.0-1.0)
    model_count: int  # number of models in ensemble
    model_ids: list[str] = field(default_factory=list)
    individual_probabilities: list[float] = field(default_factory=list)
    mode: str = "simple_average"
    predicted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ModelEnsemble:
    """Multi-model ensemble predictor.

    Modes:
    - simple_average: Equal-weight average of all model probabilities
    - accuracy_weighted: Weight by model test accuracy
    - regime_gated: Only include models trained during similar regime
    """

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        mode: str = "simple_average",
        max_models: int = MAX_ENSEMBLE_SIZE,
    ):
        if mode not in ("simple_average", "accuracy_weighted", "regime_gated"):
            raise ValueError(f"Invalid ensemble mode: {mode}")
        self._registry = registry or ModelRegistry()
        self._mode = mode
        self._max_models = min(max_models, MAX_ENSEMBLE_SIZE)
        self._model_ids: list[str] = []
        self._models: list[tuple[object, dict]] = []  # (model, manifest) pairs

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def model_count(self) -> int:
        return len(self._models)

    @property
    def model_ids(self) -> list[str]:
        return list(self._model_ids)

    def build_from_registry(
        self,
        asset_class: str = "",
        symbol: str = "",
        regime: str = "",
    ) -> int:
        """Auto-select best models from registry.

        Selection cascade:
        1. Filter by symbol if provided
        2. Filter by asset_class label if provided
        3. Sort by accuracy descending
        4. Take top max_models

        For regime_gated mode, also filter by regime metadata.

        Args:
            asset_class: Filter by asset class label.
            symbol: Filter by training symbol.
            regime: Current regime (for regime_gated mode).

        Returns:
            Number of models loaded.
        """
        all_models = self._registry.list_models()
        if not all_models:
            return 0

        candidates = all_models

        # Filter by symbol
        if symbol:
            sym_clean = symbol.replace("/", "")
            sym_matches = [
                m for m in candidates
                if m.get("symbol", "").replace("/", "") == sym_clean
            ]
            if sym_matches:
                candidates = sym_matches

        # Filter by asset class
        if asset_class and len(candidates) > self._max_models:
            ac_matches = [
                m for m in candidates
                if asset_class.lower() in (m.get("label", "") or "").lower()
            ]
            if ac_matches:
                candidates = ac_matches

        # Regime-gated: filter by regime in metadata
        if self._mode == "regime_gated" and regime:
            regime_matches = [
                m for m in candidates
                if regime.lower() in (m.get("label", "") or "").lower()
            ]
            if regime_matches:
                candidates = regime_matches

        # Sort by accuracy (descending), take top N
        candidates.sort(
            key=lambda m: m.get("metrics", {}).get("accuracy", 0),
            reverse=True,
        )
        candidates = candidates[: self._max_models]

        # Load models
        self._models.clear()
        self._model_ids.clear()
        for m in candidates:
            try:
                model, manifest = self._registry.load_model(m["model_id"])
                self._models.append((model, manifest))
                self._model_ids.append(m["model_id"])
            except (FileNotFoundError, ImportError) as e:
                logger.warning("Failed to load model %s: %s", m["model_id"], e)

        logger.info("Ensemble built: %d models (%s mode)", len(self._models), self._mode)
        return len(self._models)

    def add_model(self, model_id: str) -> bool:
        """Manually add a model to the ensemble.

        Returns:
            True if added, False if at capacity or load failed.
        """
        if len(self._models) >= self._max_models:
            logger.warning("Ensemble at capacity (%d)", self._max_models)
            return False

        if model_id in self._model_ids:
            return False

        try:
            model, manifest = self._registry.load_model(model_id)
            self._models.append((model, manifest))
            self._model_ids.append(model_id)
            return True
        except (FileNotFoundError, ImportError) as e:
            logger.warning("Failed to add model %s: %s", model_id, e)
            return False

    def predict(self, features: pd.DataFrame) -> EnsembleResult | None:
        """Generate ensemble prediction.

        Args:
            features: Feature matrix (last row used for prediction).

        Returns:
            EnsembleResult or None if no models loaded.
        """
        if not self._models:
            return None

        probabilities = []
        accuracies = []

        for model, manifest in self._models:
            try:
                if HAS_LIGHTGBM and isinstance(model, lgb.Booster):
                    raw = model.predict(features)
                    prob = float(np.array(raw).flat[-1])
                else:
                    proba = model.predict_proba(features)  # type: ignore[union-attr]
                    prob = float(proba[-1, 1]) if proba.ndim == 2 else float(proba[-1])
                probabilities.append(prob)
                accuracies.append(manifest.get("metrics", {}).get("accuracy", 0.5))
            except Exception as e:
                logger.warning("Ensemble model prediction failed: %s", e)

        if not probabilities:
            return None

        probs = np.array(probabilities)
        accs = np.array(accuracies)

        # Aggregate based on mode
        if self._mode == "accuracy_weighted" and accs.sum() > 0:
            weights = accs / accs.sum()
            agg_prob = float(np.dot(probs, weights))
        else:
            # simple_average and regime_gated (after filtering, average)
            agg_prob = float(np.mean(probs))

        # Direction and agreement
        directions = (probs >= 0.5).astype(int)
        majority_direction = int(np.round(np.mean(directions)))
        agreement_ratio = float(np.mean(directions == majority_direction))
        direction = "up" if agg_prob >= 0.5 else "down"

        return EnsembleResult(
            probability=round(agg_prob, 4),
            direction=direction,
            agreement_ratio=round(agreement_ratio, 4),
            model_count=len(probabilities),
            model_ids=list(self._model_ids[: len(probabilities)]),
            individual_probabilities=[round(p, 4) for p in probabilities],
            mode=self._mode,
        )

    def clear(self) -> None:
        """Remove all models from the ensemble."""
        self._models.clear()
        self._model_ids.clear()
