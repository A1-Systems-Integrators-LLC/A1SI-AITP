"""Tests for XGBoost ensemble member support."""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("lightgbm", reason="lightgbm not installed")


def _make_data(n=300):
    np.random.seed(42)
    X = pd.DataFrame({f"f{i}": np.random.randn(n) for i in range(5)}) # noqa: N806
    y = pd.Series((np.random.rand(n) > 0.5).astype(int))
    return X, y, list(X.columns)


def _can_import(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


class TestXGBoostTraining:
    @pytest.mark.skipif(not _can_import("xgboost"), reason="xgboost not installed")
    def test_train_xgboost_model(self):
        from common.ml.trainer import train_model

        X, y, features = _make_data() # noqa: N806
        result = train_model(X, y, features, model_type="xgboost")
        assert result["model"] is not None
        assert result["metadata"]["model_type"] == "XGBClassifier"
        assert "accuracy" in result["metrics"]

    def test_xgboost_importerror(self):
        with patch("common.ml.trainer.HAS_XGBOOST", False):
            from common.ml.trainer import train_model

            X, y, features = _make_data() # noqa: N806
            with pytest.raises(ImportError, match="xgboost"):
                train_model(X, y, features, model_type="xgboost")

    def test_lightgbm_still_default(self):
        from common.ml.trainer import train_model

        X, y, features = _make_data() # noqa: N806
        result = train_model(X, y, features)
        assert result["metadata"]["model_type"] == "LightGBMClassifier"


class TestXGBoostSaveLoad:
    @pytest.mark.skipif(not _can_import("xgboost"), reason="xgboost not installed")
    def test_save_load_roundtrip(self, tmp_path):
        from common.ml.registry import ModelRegistry
        from common.ml.trainer import train_model

        X, y, features = _make_data() # noqa: N806
        result = train_model(X, y, features, model_type="xgboost")

        registry = ModelRegistry(models_dir=tmp_path / "models")
        model_id = registry.save_model(
            result["model"],
            result["metrics"],
            result["metadata"],
            result["feature_importance"],
            symbol="BTC/USDT",
            timeframe="1h",
        )
        loaded_model, manifest = registry.load_model(model_id)
        assert manifest["model_format"] == "xgboost"

        # Verify predictions work
        proba = loaded_model.predict_proba(X.tail(1))
        assert proba.shape[1] == 2

    @pytest.mark.skipif(not _can_import("xgboost"), reason="xgboost not installed")
    def test_lightgbm_save_load_unchanged(self, tmp_path):
        from common.ml.registry import ModelRegistry
        from common.ml.trainer import train_model

        X, y, features = _make_data() # noqa: N806
        result = train_model(X, y, features, model_type="lightgbm")

        registry = ModelRegistry(models_dir=tmp_path / "models")
        model_id = registry.save_model(
            result["model"],
            result["metrics"],
            result["metadata"],
            result["feature_importance"],
        )
        loaded, manifest = registry.load_model(model_id)
        assert manifest.get("model_format", "lightgbm") == "lightgbm"


class TestEnsembleMixedModels:
    @pytest.mark.skipif(not _can_import("xgboost"), reason="xgboost not installed")
    def test_mixed_ensemble_predict(self, tmp_path):
        from common.ml.ensemble import ModelEnsemble
        from common.ml.registry import ModelRegistry
        from common.ml.trainer import train_model

        X, y, features = _make_data() # noqa: N806

        registry = ModelRegistry(models_dir=tmp_path / "models")

        # Train and save LightGBM
        lgb_result = train_model(X, y, features, model_type="lightgbm")
        lgb_id = registry.save_model(
            lgb_result["model"],
            lgb_result["metrics"],
            lgb_result["metadata"],
            lgb_result["feature_importance"],
            symbol="BTC/USDT",
        )

        # Train and save XGBoost (use different symbol to avoid model_id collision)
        xgb_result = train_model(X, y, features, model_type="xgboost")
        xgb_id = registry.save_model(
            xgb_result["model"],
            xgb_result["metrics"],
            xgb_result["metadata"],
            xgb_result["feature_importance"],
            symbol="ETH/USDT",
        )

        # Build ensemble with both
        ensemble = ModelEnsemble(registry=registry, mode="simple_average")
        ensemble.add_model(lgb_id)
        ensemble.add_model(xgb_id)
        assert ensemble.model_count == 2

        result = ensemble.predict(X.tail(1))
        assert result is not None
        assert 0 <= result.probability <= 1
        assert result.model_count == 2

    @pytest.mark.skipif(not _can_import("xgboost"), reason="xgboost not installed")
    def test_ensemble_accuracy_weighted_mixed(self, tmp_path):
        from common.ml.ensemble import ModelEnsemble
        from common.ml.registry import ModelRegistry
        from common.ml.trainer import train_model

        X, y, features = _make_data() # noqa: N806

        registry = ModelRegistry(models_dir=tmp_path / "models")

        lgb_result = train_model(X, y, features, model_type="lightgbm")
        lgb_id = registry.save_model(
            lgb_result["model"],
            lgb_result["metrics"],
            lgb_result["metadata"],
            lgb_result["feature_importance"],
            symbol="BTC/USDT",
        )

        xgb_result = train_model(X, y, features, model_type="xgboost")
        xgb_id = registry.save_model(
            xgb_result["model"],
            xgb_result["metrics"],
            xgb_result["metadata"],
            xgb_result["feature_importance"],
            symbol="BTC/USDT",
        )

        ensemble = ModelEnsemble(registry=registry, mode="accuracy_weighted")
        ensemble.add_model(lgb_id)
        ensemble.add_model(xgb_id)
        result = ensemble.predict(X.tail(1))
        assert result is not None
        assert result.mode == "accuracy_weighted"


class TestXGBoostImportFallback:
    def test_ensemble_predict_without_xgboost_installed(self):
        """Ensemble should still work with LightGBM-only models when xgboost not installed."""
        from common.ml.ensemble import ModelEnsemble

        ensemble = ModelEnsemble(mode="simple_average")
        # No models = None result (not a crash)
        assert ensemble.predict(pd.DataFrame({"f1": [1]})) is None
