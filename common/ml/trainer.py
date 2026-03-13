"""
ML Training & Prediction Pipeline
==================================
LightGBM classifier with time-series aware train/test split.
Graceful fallback when lightgbm is not installed.
"""

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import lightgbm as lgb

    HAS_LIGHTGBM = True
except ImportError:  # pragma: no cover
    HAS_LIGHTGBM = False
    lgb = None  # type: ignore[assignment]

# Default training parameters
DEFAULT_TRAIN_PARAMS = {
    "objective": "binary",
    "metric": "binary_logloss",
    "boosting_type": "gbdt",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "n_estimators": 200,
    "max_depth": 6,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "verbose": -1,
    "n_jobs": 4,  # Adjust based on available CPU cores
}


def time_series_split(
    x_data: pd.DataFrame,
    y: pd.Series,
    test_ratio: float = 0.2,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Split data chronologically — no look-ahead bias.

    Uses the last `test_ratio` fraction of data as test set.
    """
    split_idx = int(len(x_data) * (1 - test_ratio))
    x_train = x_data.iloc[:split_idx]
    x_test = x_data.iloc[split_idx:]
    y_train = y.iloc[:split_idx]
    y_test = y.iloc[split_idx:]
    return x_train, x_test, y_train, y_test


def train_model(
    x_data: pd.DataFrame,
    y: pd.Series,
    feature_names: list[str],
    params: dict | None = None,
    test_ratio: float = 0.2,
    fit_calibration: bool = False,
) -> dict:
    """Train a LightGBM classifier and return model + metadata.

    Args:
        x_data: Feature matrix (rows aligned with y).
        y: Binary target (0/1).
        feature_names: Column names for features.
        params: LightGBM parameters (overrides defaults).
        test_ratio: Fraction of data for time-series test split.
        fit_calibration: If True, fit Platt scaling on test set and include
            calibration params in metadata.

    Returns:
        dict with keys: model, metrics, metadata, feature_importance.
        If fit_calibration=True, metadata includes 'calibration' dict.

    Raises:
        ImportError: If lightgbm is not installed.
    """
    if not HAS_LIGHTGBM:
        raise ImportError(
            "lightgbm is required for ML training. Install with: pip install lightgbm"
        )

    model_params = {**DEFAULT_TRAIN_PARAMS, **(params or {})}

    # Time-series split
    x_train, x_test, y_train, y_test = time_series_split(x_data, y, test_ratio)

    logger.info(
        "Training: %d train rows, %d test rows, %d features",
        len(x_train), len(x_test), len(feature_names),
    )

    # Train
    model = lgb.LGBMClassifier(**model_params)
    model.fit(
        x_train, y_train,
        eval_set=[(x_test, y_test)],
    )

    # Evaluate on test set
    y_pred_proba = model.predict_proba(x_test)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)

    accuracy = float(np.mean(y_pred == y_test.values))
    precision = _safe_precision(y_test.values, y_pred)
    recall = _safe_recall(y_test.values, y_pred)
    f1 = _safe_f1(precision, recall)
    logloss = float(model.best_score_.get("valid_0", {}).get("binary_logloss", 0.0))

    # Feature importance
    importance = dict(zip(feature_names, map(float, model.feature_importances_)))
    top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]

    metrics = {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "logloss": round(logloss, 6),
        "train_rows": len(x_train),
        "test_rows": len(x_test),
        "n_features": len(feature_names),
    }

    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "model_type": "LightGBMClassifier",
        "params": model_params,
        "feature_names": feature_names,
        "test_ratio": test_ratio,
    }

    # Optionally fit Platt scaling calibration on test set
    if fit_calibration:
        try:
            from common.ml.calibration import PredictionCalibrator

            calibrator = PredictionCalibrator()
            a, b = calibrator.fit(y_pred_proba, y_test.values)
            metadata["calibration"] = {"a": a, "b": b}
            logger.info("Calibration fitted: a=%.6f, b=%.6f", a, b)
        except Exception as e:
            logger.warning("Calibration fitting failed: %s", e)

    logger.info(
        "Training complete: accuracy=%.4f, precision=%.4f, f1=%.4f",
        accuracy, precision, f1,
    )
    logger.info("Top features: %s", [f[0] for f in top_features[:5]])

    return {
        "model": model,
        "metrics": metrics,
        "metadata": metadata,
        "feature_importance": importance,
    }


def predict(model: object, X: pd.DataFrame) -> dict:
    """Generate predictions from a trained model.

    Args:
        model: Trained LGBMClassifier.
        X: Feature matrix.

    Returns:
        dict with probability, predicted_class, and bar count.
    """
    if not HAS_LIGHTGBM:
        raise ImportError("lightgbm is required for prediction.")

    proba = model.predict_proba(X)[:, 1]  # type: ignore[union-attr]
    predicted = (proba >= 0.5).astype(int)

    return {
        "probabilities": proba.tolist(),
        "predictions": predicted.tolist(),
        "n_bars": len(X),
        "mean_probability": round(float(np.mean(proba)), 4),
        "predicted_up_pct": round(float(np.mean(predicted)) * 100, 2),
    }


# --- Internal helpers ---

def _safe_precision(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    tp = int(np.sum((y_pred == 1) & (y_true == 1)))
    fp = int(np.sum((y_pred == 1) & (y_true == 0)))
    return tp / (tp + fp) if (tp + fp) > 0 else 0.0


def _safe_recall(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    tp = int(np.sum((y_pred == 1) & (y_true == 1)))
    fn = int(np.sum((y_pred == 0) & (y_true == 1)))
    return tp / (tp + fn) if (tp + fn) > 0 else 0.0


def _safe_f1(precision: float, recall: float) -> float:
    return (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
