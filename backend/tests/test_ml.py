"""
Tests for the ML pipeline: features, trainer, registry, and backend service.
All framework dependencies (lightgbm, etc.) are required — tests FAIL if missing.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.ml.features import (  # noqa: E402, I001
    add_lag_features,
    add_return_features,
    build_feature_matrix,
    compute_indicator_features,
    compute_target,
)
from common.ml.registry import ModelRegistry  # noqa: E402
from common.ml.trainer import time_series_split  # noqa: E402

# ── Fixtures ─────────────────────────────────────────────────────


def _make_ohlcv(n: int = 500) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    timestamps = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    prices = 42000 * np.exp(np.cumsum(np.random.normal(0, 0.01, n)))
    return pd.DataFrame(
        {
            "open": prices * np.random.uniform(0.999, 1.001, n),
            "high": prices * np.random.uniform(1.001, 1.015, n),
            "low": prices * np.random.uniform(0.985, 0.999, n),
            "close": prices,
            "volume": np.random.lognormal(15, 1, n),
        },
        index=timestamps,
    )


@pytest.fixture
def ohlcv_df():
    return _make_ohlcv(500)


@pytest.fixture
def small_ohlcv():
    return _make_ohlcv(50)


@pytest.fixture
def tmp_models_dir(tmp_path):
    d = tmp_path / "models"
    d.mkdir()
    return d


# ── Feature Engineering Tests ────────────────────────────────────


class TestComputeIndicatorFeatures:
    def test_returns_dataframe_with_expected_columns(self, ohlcv_df):
        feat = compute_indicator_features(ohlcv_df)
        assert isinstance(feat, pd.DataFrame)
        assert len(feat) == len(ohlcv_df)
        assert "rsi_14" in feat.columns
        assert "macd" in feat.columns
        assert "bb_width" in feat.columns
        assert "volume_ratio" in feat.columns
        assert "adx_14" in feat.columns

    def test_has_normalized_price_features(self, ohlcv_df):
        feat = compute_indicator_features(ohlcv_df)
        assert "close_over_sma_21" in feat.columns
        assert "close_over_ema_50" in feat.columns
        assert "ema_7_over_21" in feat.columns

    def test_produces_numeric_values(self, ohlcv_df):
        feat = compute_indicator_features(ohlcv_df)
        # After warmup, values should be numeric (not all NaN)
        non_nan = feat.iloc[200:].notna()
        assert non_nan.all().all(), "Some columns are all NaN after warmup"

    def test_small_data_produces_features(self, small_ohlcv):
        """Even small data should produce features (with NaN warmup)."""
        feat = compute_indicator_features(small_ohlcv)
        assert len(feat) == len(small_ohlcv)
        assert feat.shape[1] > 10


class TestAddLagFeatures:
    def test_default_lags(self, ohlcv_df):
        feat = compute_indicator_features(ohlcv_df)
        lagged = add_lag_features(feat)
        assert "rsi_14_lag1" in lagged.columns
        assert "rsi_14_lag5" in lagged.columns
        assert "macd_hist_lag3" in lagged.columns

    def test_custom_lag_periods(self, ohlcv_df):
        feat = compute_indicator_features(ohlcv_df)
        lagged = add_lag_features(feat, lag_periods=[1, 10])
        assert "rsi_14_lag1" in lagged.columns
        assert "rsi_14_lag10" in lagged.columns
        assert "rsi_14_lag5" not in lagged.columns

    def test_preserves_original_columns(self, ohlcv_df):
        feat = compute_indicator_features(ohlcv_df)
        original_cols = set(feat.columns)
        lagged = add_lag_features(feat)
        assert original_cols.issubset(set(lagged.columns))


class TestAddReturnFeatures:
    def test_default_return_periods(self, ohlcv_df):
        ret = add_return_features(ohlcv_df)
        assert "return_1" in ret.columns
        assert "return_10" in ret.columns
        assert "log_return_5" in ret.columns
        assert "hl_range_pct" in ret.columns

    def test_custom_periods(self, ohlcv_df):
        ret = add_return_features(ohlcv_df, periods=[2, 7])
        assert "return_2" in ret.columns
        assert "return_7" in ret.columns
        assert "return_1" not in ret.columns


class TestComputeTarget:
    def test_binary_target_values(self, ohlcv_df):
        target = compute_target(ohlcv_df, horizon=1)
        assert set(target.dropna().unique()).issubset({0.0, 1.0})

    def test_last_rows_are_nan(self, ohlcv_df):
        target = compute_target(ohlcv_df, horizon=3)
        assert target.iloc[-3:].isna().all()
        assert target.iloc[-4:].notna().iloc[0]

    def test_horizon_1_default(self, ohlcv_df):
        target = compute_target(ohlcv_df)
        assert target.iloc[-1:].isna().all()
        assert len(target.dropna()) == len(ohlcv_df) - 1


class TestBuildFeatureMatrix:
    def test_returns_correct_types(self, ohlcv_df):
        x_feat, y_target, names = build_feature_matrix(ohlcv_df)
        assert isinstance(x_feat, pd.DataFrame)
        assert isinstance(y_target, pd.Series)
        assert isinstance(names, list)
        assert len(names) == x_feat.shape[1]

    def test_no_nan_values(self, ohlcv_df):
        x_feat, y_target, _ = build_feature_matrix(ohlcv_df)
        assert x_feat.notna().all().all()
        assert y_target.notna().all()

    def test_feature_count_reasonable(self, ohlcv_df):
        x_feat, _, names = build_feature_matrix(ohlcv_df)
        # Should have indicators + lags + returns
        assert len(names) > 30

    def test_row_count_less_than_input(self, ohlcv_df):
        x_feat, y_target, _ = build_feature_matrix(ohlcv_df)
        # Rows lost to NaN warmup and target shift
        assert len(x_feat) < len(ohlcv_df)
        assert len(x_feat) > 200  # But most rows should survive

    def test_custom_config(self, ohlcv_df):
        cfg = {"lag_periods": [1], "return_periods": [1], "target_horizon": 2, "drop_na": True}
        x_feat, y_target, names = build_feature_matrix(ohlcv_df, config=cfg)
        assert "rsi_14_lag1" in names
        assert "rsi_14_lag5" not in names
        assert "return_1" in names
        assert "return_10" not in names


# ── Trainer Tests ────────────────────────────────────────────────


class TestTimeSeriesSplit:
    def test_split_preserves_order(self, ohlcv_df):
        x_feat, y_target, _ = build_feature_matrix(ohlcv_df)
        x_train, x_test, _, _ = time_series_split(x_feat, y_target, test_ratio=0.2)
        # Train should come before test chronologically
        assert x_train.index[-1] < x_test.index[0]

    def test_split_sizes(self, ohlcv_df):
        x_feat, y_target, _ = build_feature_matrix(ohlcv_df)
        x_train, x_test, _, _ = time_series_split(x_feat, y_target, test_ratio=0.3)
        total = len(x_train) + len(x_test)
        assert total == len(x_feat)
        assert abs(len(x_test) / total - 0.3) < 0.02

    def test_no_data_leakage(self, ohlcv_df):
        x_feat, y_target, _ = build_feature_matrix(ohlcv_df)
        x_train, x_test, _, _ = time_series_split(x_feat, y_target)
        # No overlapping indices
        assert len(set(x_train.index) & set(x_test.index)) == 0


class TestTrainModel:
    def test_train_returns_model_and_metrics(self, ohlcv_df):
        from common.ml.trainer import train_model

        x_feat, y_target, names = build_feature_matrix(ohlcv_df)
        result = train_model(x_feat, y_target, names)
        assert "model" in result
        assert "metrics" in result
        assert "metadata" in result
        assert "feature_importance" in result

    def test_metrics_keys(self, ohlcv_df):
        from common.ml.trainer import train_model

        x_feat, y_target, names = build_feature_matrix(ohlcv_df)
        result = train_model(x_feat, y_target, names)
        metrics = result["metrics"]
        assert "accuracy" in metrics
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1" in metrics
        assert "logloss" in metrics
        assert 0 <= metrics["accuracy"] <= 1

    def test_feature_importance_matches_features(self, ohlcv_df):
        from common.ml.trainer import train_model

        x_feat, y_target, names = build_feature_matrix(ohlcv_df)
        result = train_model(x_feat, y_target, names)
        assert set(result["feature_importance"].keys()) == set(names)

    def test_predict_function(self, ohlcv_df):
        from common.ml.trainer import predict, train_model

        x_feat, y_target, names = build_feature_matrix(ohlcv_df)
        result = train_model(x_feat, y_target, names)
        pred = predict(result["model"], x_feat.tail(20))
        assert "probabilities" in pred
        assert "predictions" in pred
        assert len(pred["probabilities"]) == 20
        assert all(0 <= p <= 1 for p in pred["probabilities"])


# ── Registry Tests ───────────────────────────────────────────────


class TestModelRegistry:
    def test_list_empty_registry(self, tmp_models_dir):
        registry = ModelRegistry(models_dir=tmp_models_dir)
        assert registry.list_models() == []

    def test_get_nonexistent_model(self, tmp_models_dir):
        registry = ModelRegistry(models_dir=tmp_models_dir)
        assert registry.get_model_detail("nonexistent") is None

    def test_delete_nonexistent_model(self, tmp_models_dir):
        registry = ModelRegistry(models_dir=tmp_models_dir)
        assert registry.delete_model("nonexistent") is False


class TestModelRegistryWithModel:
    def test_save_and_list(self, ohlcv_df, tmp_models_dir):
        from common.ml.trainer import train_model

        x_feat, y_target, names = build_feature_matrix(ohlcv_df)
        result = train_model(x_feat, y_target, names)

        registry = ModelRegistry(models_dir=tmp_models_dir)
        model_id = registry.save_model(
            model=result["model"],
            metrics=result["metrics"],
            metadata=result["metadata"],
            feature_importance=result["feature_importance"],
            symbol="BTC/USDT",
            timeframe="1h",
        )

        models = registry.list_models()
        assert len(models) == 1
        assert models[0]["model_id"] == model_id
        assert models[0]["symbol"] == "BTC/USDT"

    def test_save_and_load(self, ohlcv_df, tmp_models_dir):
        from common.ml.trainer import train_model

        x_feat, y_target, names = build_feature_matrix(ohlcv_df)
        result = train_model(x_feat, y_target, names)

        registry = ModelRegistry(models_dir=tmp_models_dir)
        model_id = registry.save_model(
            model=result["model"],
            metrics=result["metrics"],
            metadata=result["metadata"],
            feature_importance=result["feature_importance"],
        )

        loaded_model, manifest = registry.load_model(model_id)
        assert manifest["model_id"] == model_id
        assert "metrics" in manifest

    def test_get_detail(self, ohlcv_df, tmp_models_dir):
        from common.ml.trainer import train_model

        x_feat, y_target, names = build_feature_matrix(ohlcv_df)
        result = train_model(x_feat, y_target, names)

        registry = ModelRegistry(models_dir=tmp_models_dir)
        model_id = registry.save_model(
            model=result["model"],
            metrics=result["metrics"],
            metadata=result["metadata"],
            feature_importance=result["feature_importance"],
        )

        detail = registry.get_model_detail(model_id)
        assert detail is not None
        assert detail["model_id"] == model_id
        assert "feature_importance" in detail

    def test_delete_model(self, ohlcv_df, tmp_models_dir):
        from common.ml.trainer import train_model

        x_feat, y_target, names = build_feature_matrix(ohlcv_df)
        result = train_model(x_feat, y_target, names)

        registry = ModelRegistry(models_dir=tmp_models_dir)
        model_id = registry.save_model(
            model=result["model"],
            metrics=result["metrics"],
            metadata=result["metadata"],
            feature_importance=result["feature_importance"],
        )

        assert registry.delete_model(model_id) is True
        assert registry.list_models() == []
        assert registry.get_model_detail(model_id) is None


# ── Backend Service Tests (unit, no Django) ──────────────────────


class TestMLServiceImports:
    def test_ml_service_importable(self):
        """Verify the ML service module can be imported."""
        from common.ml.features import build_feature_matrix
        from common.ml.registry import ModelRegistry
        from common.ml.trainer import time_series_split

        assert callable(build_feature_matrix)
        assert callable(time_series_split)
        assert hasattr(ModelRegistry, "list_models")
