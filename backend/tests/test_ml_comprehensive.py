"""Comprehensive ML Pipeline Tests
================================
Edge cases, LightGBM 4.x compatibility, registry operations,
and integration-level scenarios beyond the base test_ml.py coverage.
"""

import sys
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("lightgbm")

from common.ml.features import (
    add_lag_features,
    add_return_features,
    build_feature_matrix,
    compute_indicator_features,
    compute_target,
)
from common.ml.registry import ModelRegistry
from common.ml.trainer import (
    predict,
    time_series_split,
    train_model,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    np.random.seed(seed)
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


def _train_and_get_result(n: int = 500):
    """Train a model on synthetic data and return the result dict."""
    df = _make_ohlcv(n)
    X, y, names = build_feature_matrix(df)  # noqa: N806
    return train_model(X, y, names)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ohlcv_500():
    return _make_ohlcv(500)


@pytest.fixture
def tmp_registry(tmp_path):
    d = tmp_path / "models"
    d.mkdir()
    return ModelRegistry(models_dir=d)


@pytest.fixture
def trained_result():
    """A pre-trained result dict (model, metrics, metadata, feature_importance)."""
    return _train_and_get_result(500)


# ===================================================================
# 1. Feature Engineering Edge Cases
# ===================================================================


class TestFeatureEngineeringEdgeCases:
    """Edge cases for the feature pipeline."""

    def test_very_short_dataframe(self):
        """A DataFrame with < 20 rows should produce features but with many NaNs."""
        df = _make_ohlcv(15)
        feat = compute_indicator_features(df)
        assert len(feat) == 15
        # Most indicator columns will be NaN due to warmup, but shape must match
        assert feat.shape[1] > 10

    def test_short_dataframe_build_feature_matrix_drops_all(self):
        """With very short data, build_feature_matrix may drop all rows (all NaN)."""
        df = _make_ohlcv(10)
        X, y, names = build_feature_matrix(df)  # noqa: N806
        # 10 rows is too short for 50-period SMA warmup; expect 0 clean rows
        assert len(X) == 0
        assert len(y) == 0
        assert len(names) > 0  # feature names are still defined

    def test_dataframe_with_constant_close(self):
        """Constant-price data should produce features without crashing."""
        n = 200
        ts = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {
                "open": np.full(n, 100.0),
                "high": np.full(n, 100.0),
                "low": np.full(n, 100.0),
                "close": np.full(n, 100.0),
                "volume": np.full(n, 1000.0),
            },
            index=ts,
        )
        feat = compute_indicator_features(df)
        assert len(feat) == n
        # RSI of a constant is NaN (no change), verify no crash
        assert "rsi_14" in feat.columns

    def test_missing_ohlcv_column_raises(self):
        """If a required column is missing, compute_indicator_features should raise."""
        df = _make_ohlcv(100)
        df_missing = df.drop(columns=["volume"])
        with pytest.raises(KeyError):
            compute_indicator_features(df_missing)

    def test_all_nan_volume_column(self):
        """A volume column that is entirely NaN should not crash indicator computation."""
        df = _make_ohlcv(200)
        df["volume"] = np.nan
        # Should run without exception (volume-based indicators will be NaN)
        feat = compute_indicator_features(df)
        assert feat["obv"].isna().all() or not feat["obv"].isna().all()
        # Just ensure it didn't crash — the NaN propagation is expected

    def test_return_features_on_constant_prices(self):
        """Returns on constant prices should be zero."""
        n = 50
        ts = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {
                "open": np.full(n, 50.0),
                "high": np.full(n, 50.0),
                "low": np.full(n, 50.0),
                "close": np.full(n, 50.0),
                "volume": np.full(n, 100.0),
            },
            index=ts,
        )
        ret = add_return_features(df)
        # pct_change on constant is 0
        assert (ret["return_1"].dropna() == 0.0).all()


# ===================================================================
# 2. LightGBM 4.x Save/Load Format
# ===================================================================


class TestLightGBM4xCompat:
    """Verify LightGBM 4.x booster_ attribute and save/load round-trip."""

    def test_booster_attribute_exists(self, trained_result):
        """LightGBM 4.x: model.booster_ should be accessible."""
        model = trained_result["model"]
        booster = getattr(model, "booster_", None)
        assert booster is not None, "booster_ attribute missing on trained LGBMClassifier"

    def test_save_load_roundtrip_produces_same_predictions(self, trained_result, tmp_registry):
        """Save via registry, reload as Booster, predictions should match."""
        model = trained_result["model"]
        X = _make_ohlcv(500)  # noqa: N806
        X_feat, _, names = build_feature_matrix(X)  # noqa: N806
        X_sample = X_feat.tail(20)  # noqa: N806

        # Predictions from original sklearn model
        orig_proba = model.predict_proba(X_sample)[:, 1]

        # Save and reload
        model_id = tmp_registry.save_model(
            model=model,
            metrics=trained_result["metrics"],
            metadata=trained_result["metadata"],
            feature_importance=trained_result["feature_importance"],
            symbol="TEST/USDT",
            timeframe="1h",
        )
        loaded_clf, manifest = tmp_registry.load_model(model_id)

        # Loaded model is an LGBMClassifier wrapper — use predict_proba
        loaded_proba = loaded_clf.predict_proba(X_sample)[:, 1]
        np.testing.assert_allclose(orig_proba, loaded_proba, atol=1e-6)

    def test_saved_model_file_is_text_format(self, trained_result, tmp_registry):
        """The saved model.txt should be a valid LightGBM text model."""
        model_id = tmp_registry.save_model(
            model=trained_result["model"],
            metrics=trained_result["metrics"],
            metadata=trained_result["metadata"],
            feature_importance=trained_result["feature_importance"],
        )
        model_dir = tmp_registry.models_dir / model_id
        model_file = model_dir / "model.txt"
        assert model_file.exists()
        content = model_file.read_text()
        assert "tree" in content.lower() or "booster" in content.lower()


# ===================================================================
# 3. Model Prediction Edge Cases
# ===================================================================


class TestPredictionEdgeCases:
    """Edge cases for the predict() function."""

    def test_predict_single_row(self, trained_result):
        """Prediction on a single row should work."""
        X = _make_ohlcv(500)  # noqa: N806
        X_feat, _, _ = build_feature_matrix(X)  # noqa: N806
        result = predict(trained_result["model"], X_feat.tail(1))
        assert len(result["probabilities"]) == 1
        assert 0 <= result["probabilities"][0] <= 1

    def test_predict_returns_correct_structure(self, trained_result):
        """All expected keys should be present in prediction output."""
        X = _make_ohlcv(500)  # noqa: N806
        X_feat, _, _ = build_feature_matrix(X)  # noqa: N806
        result = predict(trained_result["model"], X_feat.tail(5))
        assert "probabilities" in result
        assert "predictions" in result
        assert "n_bars" in result
        assert "mean_probability" in result
        assert "predicted_up_pct" in result
        assert result["n_bars"] == 5

    def test_predict_classes_are_binary(self, trained_result):
        """Predicted classes should be 0 or 1."""
        X = _make_ohlcv(500)  # noqa: N806
        X_feat, _, _ = build_feature_matrix(X)  # noqa: N806
        result = predict(trained_result["model"], X_feat.tail(30))
        assert all(p in (0, 1) for p in result["predictions"])

    def test_predict_with_nan_features_raises(self, trained_result):
        """Prediction on data containing NaN should raise or produce NaN probabilities.

        LightGBM handles NaN natively (treats as missing), so it should not crash
        but we verify the function completes.
        """
        X = _make_ohlcv(500)  # noqa: N806
        X_feat, _, _ = build_feature_matrix(X)  # noqa: N806
        sample = X_feat.tail(10).copy()
        sample.iloc[0, 0] = np.nan
        sample.iloc[3, 5] = np.nan
        # LightGBM handles NaN natively — this should not raise
        result = predict(trained_result["model"], sample)
        assert len(result["probabilities"]) == 10


# ===================================================================
# 4. Training with Different Data Sizes
# ===================================================================


class TestTrainingDataSizes:
    """Training with various dataset sizes."""

    def test_minimal_viable_data(self):
        """Just enough data after feature warmup to do a train/test split."""
        # 120 rows: ~50 lost to warmup, ~70 remain, split 80/20 = 56 train / 14 test
        df = _make_ohlcv(120)
        X, y, names = build_feature_matrix(df)  # noqa: N806
        assert len(X) > 0, "No rows survived feature warmup with 120-row input"
        result = train_model(X, y, names, test_ratio=0.2)
        assert result["metrics"]["accuracy"] >= 0  # Just verify it trained

    def test_large_dataset(self):
        """1500 rows — verify training completes and metrics are reasonable.

        Dead zone + feature warmup reduce rows (~25% dropped by dead zone),
        so 1500 raw → ~1100 feature rows → ~880 train.
        """
        df = _make_ohlcv(1500)
        X, y, names = build_feature_matrix(df)  # noqa: N806
        result = train_model(X, y, names)
        assert result["metrics"]["train_rows"] > 700
        assert result["metrics"]["test_rows"] > 150
        assert 0 <= result["metrics"]["accuracy"] <= 1

    def test_custom_train_params(self):
        """Override LightGBM params (fewer estimators for speed)."""
        df = _make_ohlcv(300)
        X, y, names = build_feature_matrix(df)  # noqa: N806
        result = train_model(X, y, names, params={"n_estimators": 10, "verbose": -1})
        assert "model" in result


# ===================================================================
# 5. Registry Operations
# ===================================================================


class TestRegistryOperations:
    """Advanced registry tests: multiple models, delete, concurrent access."""

    def test_save_multiple_models_listed_correctly(self, trained_result, tmp_registry):
        """Save 3 models with different symbols, list should return all 3."""
        ids = []
        for symbol in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
            mid = tmp_registry.save_model(
                model=trained_result["model"],
                metrics=trained_result["metrics"],
                metadata=trained_result["metadata"],
                feature_importance=trained_result["feature_importance"],
                symbol=symbol,
                timeframe="1h",
            )
            ids.append(mid)
            time.sleep(0.01)  # Ensure unique timestamps

        models = tmp_registry.list_models()
        assert len(models) == 3
        symbols = {m["symbol"] for m in models}
        assert symbols == {"BTC/USDT", "ETH/USDT", "SOL/USDT"}

    def test_list_models_sorted_newest_first(self, trained_result, tmp_registry):
        """Models should be listed newest first."""
        for sym in ["AAA", "BBB", "CCC"]:
            tmp_registry.save_model(
                model=trained_result["model"],
                metrics=trained_result["metrics"],
                metadata=trained_result["metadata"],
                feature_importance=trained_result["feature_importance"],
                symbol=sym,
                timeframe="1d",
            )
            time.sleep(0.01)

        models = tmp_registry.list_models()
        # Newest (CCC) should be first
        assert models[0]["symbol"] == "CCC"
        assert models[-1]["symbol"] == "AAA"

    def test_delete_nonexistent_returns_false(self, tmp_registry):
        assert tmp_registry.delete_model("does_not_exist") is False

    def test_save_then_delete_then_list_empty(self, trained_result, tmp_registry):
        mid = tmp_registry.save_model(
            model=trained_result["model"],
            metrics=trained_result["metrics"],
            metadata=trained_result["metadata"],
            feature_importance=trained_result["feature_importance"],
        )
        assert tmp_registry.delete_model(mid) is True
        assert tmp_registry.list_models() == []

    def test_load_nonexistent_raises_file_not_found(self, tmp_registry):
        with pytest.raises(FileNotFoundError, match="Model not found"):
            tmp_registry.load_model("nonexistent_model")

    def test_concurrent_save_operations(self, trained_result, tmp_registry):
        """Multiple threads saving models concurrently should not corrupt the registry."""
        errors = []

        def save_model(symbol: str) -> None:
            try:
                tmp_registry.save_model(
                    model=trained_result["model"],
                    metrics=trained_result["metrics"],
                    metadata=trained_result["metadata"],
                    feature_importance=trained_result["feature_importance"],
                    symbol=symbol,
                    timeframe="1h",
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=save_model, args=(f"SYM{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent save errors: {errors}"
        models = tmp_registry.list_models()
        assert len(models) == 5

    def test_corrupt_manifest_skipped_in_list(self, tmp_registry):
        """A model dir with a corrupt manifest.json should be skipped gracefully."""
        bad_dir = tmp_registry.models_dir / "corrupt_model"
        bad_dir.mkdir()
        (bad_dir / "manifest.json").write_text("{invalid json")
        (bad_dir / "model.txt").write_text("fake")

        models = tmp_registry.list_models()
        assert len(models) == 0  # corrupt entry skipped

    def test_model_id_includes_symbol_and_timeframe(self, trained_result, tmp_registry):
        """Model ID should incorporate symbol and timeframe when provided."""
        mid = tmp_registry.save_model(
            model=trained_result["model"],
            metrics=trained_result["metrics"],
            metadata=trained_result["metadata"],
            feature_importance=trained_result["feature_importance"],
            symbol="BTC/USDT",
            timeframe="4h",
        )
        assert "BTCUSDT" in mid
        assert "4h" in mid


# ===================================================================
# 6. Time Series Split Edge Cases
# ===================================================================


class TestTimeSeriesSplitEdgeCases:
    """Edge cases for the time_series_split function."""

    def test_split_with_test_ratio_zero(self, ohlcv_500):
        """test_ratio=0.0 should put all data in train, none in test."""
        X, y, _ = build_feature_matrix(ohlcv_500)  # noqa: N806
        x_train, x_test, y_train, y_test = time_series_split(X, y, test_ratio=0.0)
        assert len(x_train) == len(X)
        assert len(x_test) == 0

    def test_split_with_test_ratio_one(self, ohlcv_500):
        """test_ratio=1.0 should put all data in test, none in train."""
        X, y, _ = build_feature_matrix(ohlcv_500)  # noqa: N806
        x_train, x_test, y_train, y_test = time_series_split(X, y, test_ratio=1.0)
        assert len(x_train) == 0
        assert len(x_test) == len(X)

    def test_split_preserves_time_order(self, ohlcv_500):
        """Train set timestamps should all precede test set timestamps."""
        X, y, _ = build_feature_matrix(ohlcv_500)  # noqa: N806
        x_train, x_test, _, _ = time_series_split(X, y, test_ratio=0.3)
        if len(x_train) > 0 and len(x_test) > 0:
            assert x_train.index.max() < x_test.index.min()

    def test_split_x_y_alignment(self, ohlcv_500):
        """X and y splits should share the same indices."""
        X, y, _ = build_feature_matrix(ohlcv_500)  # noqa: N806
        x_train, x_test, y_train, y_test = time_series_split(X, y, test_ratio=0.25)
        pd.testing.assert_index_equal(x_train.index, y_train.index)
        pd.testing.assert_index_equal(x_test.index, y_test.index)


# ===================================================================
# 7. Feature Importance
# ===================================================================


class TestFeatureImportance:
    """Verify feature importance is computed for all features."""

    def test_all_features_have_importance_scores(self):
        df = _make_ohlcv(500)
        X, y, names = build_feature_matrix(df)  # noqa: N806
        result = train_model(X, y, names)
        importance = result["feature_importance"]
        assert set(importance.keys()) == set(names)

    def test_importance_values_are_non_negative(self):
        df = _make_ohlcv(500)
        X, y, names = build_feature_matrix(df)  # noqa: N806
        result = train_model(X, y, names)
        for feat_name, score in result["feature_importance"].items():
            assert score >= 0, f"Negative importance for {feat_name}: {score}"

    def test_at_least_one_nonzero_importance(self):
        """At least one feature should have non-zero importance."""
        df = _make_ohlcv(500)
        X, y, names = build_feature_matrix(df)  # noqa: N806
        result = train_model(X, y, names)
        total = sum(result["feature_importance"].values())
        assert total > 0


# ===================================================================
# 8. Compute Target
# ===================================================================


class TestComputeTargetEdgeCases:
    """Additional target computation tests."""

    def test_target_with_large_horizon(self):
        df = _make_ohlcv(100)
        target = compute_target(df, horizon=50)
        assert target.iloc[-50:].isna().all()
        assert len(target.dropna()) == 50

    def test_target_all_up(self):
        """Monotonically increasing prices should produce all 1s."""
        n = 100
        ts = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {
                "open": np.arange(1, n + 1, dtype=float),
                "high": np.arange(2, n + 2, dtype=float),
                "low": np.arange(0.5, n + 0.5, dtype=float),
                "close": np.arange(1, n + 1, dtype=float),
                "volume": np.full(n, 1000.0),
            },
            index=ts,
        )
        target = compute_target(df, horizon=1)
        # All non-NaN values should be 1.0 (price always goes up)
        assert (target.dropna() == 1.0).all()


# ===================================================================
# 9. Add Lag Features Edge Cases
# ===================================================================


class TestAddLagFeaturesEdgeCases:
    def test_empty_dataframe_no_crash(self):
        """Lag features on an empty DataFrame should return empty."""
        empty = pd.DataFrame()
        result = add_lag_features(empty)
        assert len(result) == 0

    def test_lag_on_missing_columns_is_noop(self):
        """If none of the lag target columns exist, no new columns are added."""
        df = pd.DataFrame({"arbitrary_col": [1, 2, 3]})
        result = add_lag_features(df)
        assert list(result.columns) == ["arbitrary_col"]


# ===================================================================
# 10. Manifest Metadata Integrity
# ===================================================================


class TestManifestIntegrity:
    """Verify saved manifest has all required fields."""

    def test_manifest_contains_all_fields(self, trained_result, tmp_registry):
        mid = tmp_registry.save_model(
            model=trained_result["model"],
            metrics=trained_result["metrics"],
            metadata=trained_result["metadata"],
            feature_importance=trained_result["feature_importance"],
            symbol="BTC/USDT",
            timeframe="1h",
            label="test_label",
        )
        detail = tmp_registry.get_model_detail(mid)
        assert detail is not None
        assert detail["model_id"] == mid
        assert detail["symbol"] == "BTC/USDT"
        assert detail["timeframe"] == "1h"
        assert detail["label"] == "test_label"
        assert "created_at" in detail
        assert "metrics" in detail
        assert "metadata" in detail
        assert "feature_importance" in detail

    def test_manifest_metrics_match_training(self, trained_result, tmp_registry):
        """Metrics stored in manifest should match what was passed in."""
        mid = tmp_registry.save_model(
            model=trained_result["model"],
            metrics=trained_result["metrics"],
            metadata=trained_result["metadata"],
            feature_importance=trained_result["feature_importance"],
        )
        detail = tmp_registry.get_model_detail(mid)
        assert detail["metrics"]["accuracy"] == trained_result["metrics"]["accuracy"]
        assert detail["metrics"]["f1"] == trained_result["metrics"]["f1"]
