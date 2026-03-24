"""ML Training & Prediction Pipeline
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

try:
    import xgboost as xgb

    HAS_XGBOOST = True
except ImportError:  # pragma: no cover
    HAS_XGBOOST = False
    xgb = None  # type: ignore[assignment]

DEFAULT_XGB_PARAMS = {
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "max_depth": 6,
    "learning_rate": 0.05,
    "n_estimators": 200,
    "min_child_weight": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "verbosity": 0,
    "n_jobs": 4,
    "use_label_encoder": False,
}

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
    "is_unbalance": True,  # Handle class imbalance — prevents "always predict up" bias
    "verbose": -1,
    "n_jobs": 4,  # Adjust based on available CPU cores
}


def cross_validate(
    x_data: pd.DataFrame,
    y: pd.Series,
    feature_names: list[str],
    params: dict | None = None,
    cv_splits: int = 5,
) -> dict:
    """Run TimeSeriesSplit cross-validation and return per-fold metrics.

    Args:
        x_data: Feature matrix.
        y: Binary target.
        feature_names: Column names.
        params: LightGBM parameters.
        cv_splits: Number of CV folds.

    Returns:
        dict with per_fold metrics, mean, and std.
    """
    if not HAS_LIGHTGBM:
        raise ImportError("lightgbm is required for ML cross-validation.")

    from sklearn.model_selection import TimeSeriesSplit

    model_params = {**DEFAULT_TRAIN_PARAMS, **(params or {})}
    tscv = TimeSeriesSplit(n_splits=cv_splits)

    fold_metrics = []
    for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(x_data)):
        x_train = x_data.iloc[train_idx]
        x_test = x_data.iloc[test_idx]
        y_train = y.iloc[train_idx]
        y_test = y.iloc[test_idx]

        model = lgb.LGBMClassifier(**model_params)
        model.fit(x_train, y_train, eval_set=[(x_test, y_test)])

        y_pred_proba = model.predict_proba(x_test)[:, 1]
        y_pred = (y_pred_proba >= 0.5).astype(int)

        accuracy = float(np.mean(y_pred == y_test.values))
        precision = _safe_precision(y_test.values, y_pred)
        recall = _safe_recall(y_test.values, y_pred)
        f1 = _safe_f1(precision, recall)

        fold_metrics.append({
            "fold": fold_idx + 1,
            "train_size": len(train_idx),
            "test_size": len(test_idx),
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        })

        logger.info("CV fold %d/%d: accuracy=%.4f, f1=%.4f", fold_idx + 1, cv_splits, accuracy, f1)

    # Aggregate
    accs = [f["accuracy"] for f in fold_metrics]
    f1s = [f["f1"] for f in fold_metrics]

    return {
        "cv_splits": cv_splits,
        "per_fold": fold_metrics,
        "mean_accuracy": round(float(np.mean(accs)), 4),
        "std_accuracy": round(float(np.std(accs)), 4),
        "mean_f1": round(float(np.mean(f1s)), 4),
        "std_f1": round(float(np.std(f1s)), 4),
    }


def tune_hyperparameters(
    x_data: pd.DataFrame,
    y: pd.Series,
    feature_names: list[str],
    n_trials: int = 50,
    timeout: int = 600,
    cv_splits: int = 3,
) -> dict:
    """Bayesian hyperparameter tuning with Optuna + TimeSeriesSplit.

    Args:
        x_data: Feature matrix.
        y: Binary target.
        feature_names: Column names.
        n_trials: Number of Optuna trials.
        timeout: Max seconds for tuning.
        cv_splits: CV folds for each trial.

    Returns:
        dict with best_params, best_score, n_trials_completed.

    Raises:
        ImportError: If optuna or lightgbm not installed.
    """
    if not HAS_LIGHTGBM:
        raise ImportError("lightgbm is required for hyperparameter tuning.")

    try:
        import optuna
    except ImportError as err:
        raise ImportError(
            "optuna is required for hyperparameter tuning. Install with: pip install optuna"
        ) from err

    from sklearn.model_selection import TimeSeriesSplit

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "boosting_type": "gbdt",
            "num_leaves": trial.suggest_int("num_leaves", 15, 63),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 50, 500),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
            "verbose": -1,
            "n_jobs": 4,
        }

        tscv = TimeSeriesSplit(n_splits=cv_splits)
        scores = []

        for train_idx, test_idx in tscv.split(x_data):
            x_train = x_data.iloc[train_idx]
            x_test = x_data.iloc[test_idx]
            y_train = y.iloc[train_idx]
            y_test = y.iloc[test_idx]

            model = lgb.LGBMClassifier(**params)
            model.fit(x_train, y_train, eval_set=[(x_test, y_test)])
            y_pred = (model.predict_proba(x_test)[:, 1] >= 0.5).astype(int)
            scores.append(float(np.mean(y_pred == y_test.values)))

        return float(np.mean(scores))

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, timeout=timeout)

    best = study.best_params
    # Merge with fixed params
    best["objective"] = "binary"
    best["metric"] = "binary_logloss"
    best["boosting_type"] = "gbdt"
    best["verbose"] = -1
    best["n_jobs"] = 4

    logger.info(
        "Optuna tuning complete: %d trials, best accuracy=%.4f",
        len(study.trials),
        study.best_value,
    )

    return {
        "best_params": best,
        "best_score": round(study.best_value, 4),
        "n_trials_completed": len(study.trials),
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
    cv_splits: int = 0,
    tune: bool = False,
    model_type: str = "lightgbm",
) -> dict:
    """Train a LightGBM or XGBoost classifier and return model + metadata.

    Args:
        x_data: Feature matrix (rows aligned with y).
        y: Binary target (0/1).
        feature_names: Column names for features.
        params: Model parameters (overrides defaults).
        test_ratio: Fraction of data for time-series test split.
        fit_calibration: If True, fit Platt scaling on test set and include
            calibration params in metadata.
        model_type: "lightgbm" (default) or "xgboost".

    Returns:
        dict with keys: model, metrics, metadata, feature_importance.
        If fit_calibration=True, metadata includes 'calibration' dict.

    Raises:
        ImportError: If required library is not installed.

    """
    if model_type == "xgboost":
        if not HAS_XGBOOST:
            raise ImportError(
                "xgboost is required. Install with: pip install xgboost",
            )
    elif not HAS_LIGHTGBM:
        raise ImportError(
            "lightgbm is required for ML training. Install with: pip install lightgbm",
        )

    model_params = {**DEFAULT_TRAIN_PARAMS, **(params or {})}

    # Optional hyperparameter tuning
    tune_result = None
    if tune:
        try:
            tune_result = tune_hyperparameters(x_data, y, feature_names)
            model_params = tune_result["best_params"]
            logger.info("Using Optuna-tuned params (score=%.4f)", tune_result["best_score"])
        except ImportError:
            logger.warning("Optuna not installed, skipping hyperparameter tuning")
        except Exception as e:
            logger.warning("Hyperparameter tuning failed: %s", e)

    # Time-series split
    x_train, x_test, y_train, y_test = time_series_split(x_data, y, test_ratio)

    logger.info(
        "Training: %d train rows, %d test rows, %d features",
        len(x_train),
        len(x_test),
        len(feature_names),
    )

    # Train
    if model_type == "xgboost":
        # Use tuned params if Optuna ran, otherwise merge defaults with user params
        if tune_result and model_params:
            # Map tuned LightGBM params to XGBoost equivalents where possible
            xgb_params = {**DEFAULT_XGB_PARAMS}
            param_map = {
                "learning_rate": "learning_rate",
                "n_estimators": "n_estimators",
                "max_depth": "max_depth",
                "min_child_weight": "min_child_weight",
                "subsample": "subsample",
                "colsample_bytree": "colsample_bytree",
                "reg_alpha": "reg_alpha",
                "reg_lambda": "reg_lambda",
            }
            for lgb_key, xgb_key in param_map.items():
                if lgb_key in model_params:
                    xgb_params[xgb_key] = model_params[lgb_key]
        else:
            xgb_params = {**DEFAULT_XGB_PARAMS, **(params or {})}
        model = xgb.XGBClassifier(**xgb_params)
        model.fit(x_train, y_train, eval_set=[(x_test, y_test)], verbose=False)
    else:
        # Default LightGBM
        model = lgb.LGBMClassifier(**model_params)
        model.fit(
            x_train,
            y_train,
            eval_set=[(x_test, y_test)],
            callbacks=[lgb.early_stopping(20)],
        )

    # Evaluate on test set
    y_pred_proba = model.predict_proba(x_test)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)

    accuracy = float(np.mean(y_pred == y_test.values))
    precision = _safe_precision(y_test.values, y_pred)
    recall = _safe_recall(y_test.values, y_pred)
    f1 = _safe_f1(precision, recall)

    if model_type == "xgboost":
        # XGBoost stores eval results differently
        evals_result = getattr(model, "evals_result_", None) or {}
        validation = evals_result.get("validation_0", {})
        logloss_vals = validation.get("logloss", [0.0])
        logloss = float(logloss_vals[-1]) if logloss_vals else 0.0
    else:
        logloss = float(model.best_score_.get("valid_0", {}).get("binary_logloss", 0.0))

    # Feature importance
    importance = dict(zip(feature_names, map(float, model.feature_importances_), strict=False))
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
        "model_type": "XGBClassifier" if model_type == "xgboost" else "LightGBMClassifier",
        "params": xgb_params if model_type == "xgboost" else model_params,
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

    if tune_result:
        metadata["tuning"] = tune_result

    logger.info(
        "Training complete: accuracy=%.4f, precision=%.4f, f1=%.4f",
        accuracy,
        precision,
        f1,
    )
    logger.info("Top features: %s", [f[0] for f in top_features[:5]])

    # Optional cross-validation
    cv_result = None
    if cv_splits > 0:
        try:
            cv_result = cross_validate(
                x_data, y, feature_names, params=model_params, cv_splits=cv_splits,
            )
            metrics["cv_mean_accuracy"] = cv_result["mean_accuracy"]
            metrics["cv_std_accuracy"] = cv_result["std_accuracy"]
            logger.info(
                "CV results: mean_accuracy=%.4f ±%.4f",
                cv_result["mean_accuracy"], cv_result["std_accuracy"],
            )
        except Exception as e:
            logger.warning("Cross-validation failed: %s", e)

    return {
        "model": model,
        "metrics": metrics,
        "metadata": metadata,
        "feature_importance": importance,
    }


def predict(model: object, X: pd.DataFrame) -> dict:  # noqa: N803
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
