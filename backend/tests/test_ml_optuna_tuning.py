"""Tests for Optuna hyperparameter tuning."""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("lightgbm", reason="lightgbm not installed")
pytest.importorskip("sklearn", reason="scikit-learn not installed")


def _can_import(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _make_data(n=300):
    np.random.seed(42)
    X = pd.DataFrame({f"f{i}": np.random.randn(n) for i in range(5)}) # noqa: N806
    y = pd.Series((np.random.rand(n) > 0.5).astype(int))
    return X, y, list(X.columns)


class TestTuneHyperparameters:
    @pytest.mark.skipif(
        not _can_import("optuna"),
        reason="optuna not installed",
    )
    def test_returns_expected_keys(self):
        from common.ml.trainer import tune_hyperparameters
        X, y, features = _make_data() # noqa: N806
        result = tune_hyperparameters(X, y, features, n_trials=3, timeout=60, cv_splits=2)
        assert "best_params" in result
        assert "best_score" in result
        assert "n_trials_completed" in result

    @pytest.mark.skipif(
        not _can_import("optuna"),
        reason="optuna not installed",
    )
    def test_best_params_has_lgb_keys(self):
        from common.ml.trainer import tune_hyperparameters
        X, y, features = _make_data() # noqa: N806
        result = tune_hyperparameters(X, y, features, n_trials=2, timeout=30, cv_splits=2)
        params = result["best_params"]
        assert "num_leaves" in params
        assert "learning_rate" in params
        assert "objective" in params

    @pytest.mark.skipif(
        not _can_import("optuna"),
        reason="optuna not installed",
    )
    def test_timeout_respected(self):
        from common.ml.trainer import tune_hyperparameters
        X, y, features = _make_data() # noqa: N806
        # Very short timeout — should complete quickly
        result = tune_hyperparameters(X, y, features, n_trials=100, timeout=5, cv_splits=2)
        assert result["n_trials_completed"] >= 1

    def test_importerror_without_lightgbm(self):
        with patch("common.ml.trainer.HAS_LIGHTGBM", False):
            from common.ml.trainer import tune_hyperparameters
            X, y, features = _make_data() # noqa: N806
            with pytest.raises(ImportError):
                tune_hyperparameters(X, y, features)

    def test_importerror_without_optuna(self):
        # Simulate optuna not importable
        with patch.dict("sys.modules", {"optuna": None}):
            X, y, features = _make_data() # noqa: N806
            with pytest.raises(ImportError, match="optuna"):
                # Need fresh import since optuna is imported inside the function
                from common.ml.trainer import tune_hyperparameters
                tune_hyperparameters(X, y, features)


class TestTrainModelWithTune:
    @pytest.mark.skipif(
        not _can_import("optuna"),
        reason="optuna not installed",
    )
    def test_tune_true_uses_tuned_params(self):
        from common.ml.trainer import train_model
        X, y, features = _make_data() # noqa: N806
        with patch("common.ml.trainer.tune_hyperparameters") as mock_tune:
            mock_tune.return_value = {
                "best_params": {
                    "objective": "binary",
                    "metric": "binary_logloss",
                    "boosting_type": "gbdt",
                    "num_leaves": 20,
                    "learning_rate": 0.1,
                    "n_estimators": 100,
                    "max_depth": 5,
                    "min_child_samples": 10,
                    "subsample": 0.8,
                    "colsample_bytree": 0.8,
                    "reg_alpha": 0.1,
                    "reg_lambda": 0.1,
                    "verbose": -1,
                    "n_jobs": 4,
                },
                "best_score": 0.55,
                "n_trials_completed": 3,
            }
            result = train_model(X, y, features, tune=True)
            mock_tune.assert_called_once()
            assert "tuning" in result["metadata"]

    def test_tune_false_no_tuning(self):
        from common.ml.trainer import train_model
        X, y, features = _make_data() # noqa: N806
        result = train_model(X, y, features, tune=False)
        assert "tuning" not in result["metadata"]

    def test_tune_optuna_import_error_graceful(self):
        from common.ml.trainer import train_model
        X, y, features = _make_data() # noqa: N806
        with patch("common.ml.trainer.tune_hyperparameters", side_effect=ImportError("no optuna")):
            result = train_model(X, y, features, tune=True)
            # Should still complete without tuning
            assert result["model"] is not None
