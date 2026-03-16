"""Tests for ML cross-validation with TimeSeriesSplit."""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# Ensure common modules are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("lightgbm", reason="lightgbm not installed")
pytest.importorskip("sklearn", reason="scikit-learn not installed")

from common.ml.trainer import cross_validate, train_model


def _make_data(n=500):
    """Generate synthetic feature matrix and binary target."""
    np.random.seed(42)
    X = pd.DataFrame({ # noqa: N806
        "f1": np.random.randn(n),
        "f2": np.random.randn(n),
        "f3": np.random.randn(n),
        "f4": np.random.randn(n),
        "f5": np.random.randn(n),
    })
    y = pd.Series((np.random.rand(n) > 0.5).astype(int))
    return X, y, list(X.columns)


class TestCrossValidate:
    def test_returns_expected_keys(self):
        X, y, features = _make_data() # noqa: N806
        result = cross_validate(X, y, features, cv_splits=3)
        assert "cv_splits" in result
        assert "per_fold" in result
        assert "mean_accuracy" in result
        assert "std_accuracy" in result
        assert result["cv_splits"] == 3

    def test_fold_count_matches(self):
        X, y, features = _make_data() # noqa: N806
        result = cross_validate(X, y, features, cv_splits=4)
        assert len(result["per_fold"]) == 4

    def test_monotonic_train_sizes(self):
        X, y, features = _make_data() # noqa: N806
        result = cross_validate(X, y, features, cv_splits=5)
        train_sizes = [f["train_size"] for f in result["per_fold"]]
        assert train_sizes == sorted(train_sizes)

    def test_mean_std_are_floats(self):
        X, y, features = _make_data() # noqa: N806
        result = cross_validate(X, y, features, cv_splits=3)
        assert isinstance(result["mean_accuracy"], float)
        assert isinstance(result["std_accuracy"], float)
        assert 0 <= result["mean_accuracy"] <= 1
        assert result["std_accuracy"] >= 0

    def test_per_fold_has_required_keys(self):
        X, y, features = _make_data() # noqa: N806
        result = cross_validate(X, y, features, cv_splits=3)
        for fold in result["per_fold"]:
            assert "fold" in fold
            assert "accuracy" in fold
            assert "precision" in fold
            assert "recall" in fold
            assert "f1" in fold

    def test_importerror_without_lightgbm(self):
        with patch("common.ml.trainer.HAS_LIGHTGBM", False):
            X, y, features = _make_data() # noqa: N806
            with pytest.raises(ImportError):
                cross_validate(X, y, features)


class TestTrainModelWithCV:
    def test_cv_splits_zero_no_cv(self):
        X, y, features = _make_data() # noqa: N806
        result = train_model(X, y, features, cv_splits=0)
        assert "cv_mean_accuracy" not in result["metrics"]

    def test_cv_splits_positive_adds_metrics(self):
        X, y, features = _make_data() # noqa: N806
        result = train_model(X, y, features, cv_splits=3)
        assert "cv_mean_accuracy" in result["metrics"]
        assert "cv_std_accuracy" in result["metrics"]
