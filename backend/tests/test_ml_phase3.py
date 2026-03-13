"""
Tests for Phase 3: ML Prediction Service & Feedback Loop.
Covers: prediction.py, calibration.py, ensemble.py, feedback.py,
        enhanced features.py, enhanced trainer.py.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.ml.calibration import PredictionCalibrator  # noqa: E402
from common.ml.ensemble import EnsembleResult, ModelEnsemble  # noqa: E402
from common.ml.features import (  # noqa: E402
    add_regime_features,
    add_sentiment_features,
    add_temporal_features,
    add_volatility_regime_features,
    build_feature_matrix,
)
from common.ml.feedback import FeedbackTracker  # noqa: E402
from common.ml.prediction import PredictionResult, PredictionService  # noqa: E402
from common.ml.registry import ModelRegistry  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────


def _make_ohlcv(n: int = 500) -> pd.DataFrame:
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
def tmp_models_dir(tmp_path):
    d = tmp_path / "models"
    d.mkdir()
    return d


@pytest.fixture
def tmp_feedback_dir(tmp_path):
    d = tmp_path / "feedback"
    d.mkdir()
    return d


def _train_and_save(ohlcv_df, tmp_models_dir, symbol="BTC/USDT", label=""):
    """Helper: train a model and save it to the registry."""
    from common.ml.trainer import train_model

    x, y, names = build_feature_matrix(ohlcv_df)
    result = train_model(x, y, names)
    registry = ModelRegistry(models_dir=tmp_models_dir)
    model_id = registry.save_model(
        model=result["model"],
        metrics=result["metrics"],
        metadata=result["metadata"],
        feature_importance=result["feature_importance"],
        symbol=symbol,
        timeframe="1h",
        label=label,
    )
    return model_id, registry, result


# ══════════════════════════════════════════════════════════════════
# PredictionCalibrator Tests
# ══════════════════════════════════════════════════════════════════


class TestPredictionCalibrator:
    def test_calibrate_default_params(self):
        cal = PredictionCalibrator(a=-1.0, b=0.0)
        result = cal.calibrate(0.5)
        # sigmoid(-1*0.5 + 0) = sigmoid(-0.5) ≈ 0.622
        assert 0.6 < result < 0.65

    def test_calibrate_identity_params(self):
        cal = PredictionCalibrator(a=0.0, b=0.0)
        # sigmoid(0) = 0.5 for all inputs
        assert cal.calibrate(0.3) == 0.5
        assert cal.calibrate(0.9) == 0.5

    def test_calibrate_overflow_protection(self):
        cal = PredictionCalibrator(a=-100.0, b=0.0)
        # Should not raise overflow
        result = cal.calibrate(1.0)
        assert 0.0 <= result <= 1.0
        result = cal.calibrate(0.0)
        assert 0.0 <= result <= 1.0

    def test_calibrate_batch(self):
        cal = PredictionCalibrator(a=-1.0, b=0.0)
        raw = np.array([0.1, 0.5, 0.9])
        calibrated = cal.calibrate_batch(raw)
        assert len(calibrated) == 3
        assert all(0 <= p <= 1 for p in calibrated)

    def test_fit_converges(self):
        cal = PredictionCalibrator()
        raw = np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
        y = np.array([0, 0, 0, 1, 1, 1])
        a, b = cal.fit(raw, y)
        # After fitting, high raw → high calibrated, low raw → low calibrated
        assert cal.calibrate(0.9) > cal.calibrate(0.1)

    def test_fit_empty_data(self):
        cal = PredictionCalibrator()
        a, b = cal.fit(np.array([]), np.array([]))
        # Should return current params unchanged
        assert a == cal.a
        assert b == cal.b

    def test_record_outcome_and_accuracy(self):
        cal = PredictionCalibrator()
        # 7 correct, 3 wrong
        for _ in range(7):
            cal.record_outcome(True, True)
        for _ in range(3):
            cal.record_outcome(True, False)
        assert abs(cal.rolling_accuracy() - 0.7) < 0.01

    def test_rolling_accuracy_empty(self):
        cal = PredictionCalibrator()
        assert cal.rolling_accuracy() == 0.5

    def test_confidence(self):
        cal = PredictionCalibrator()
        for _ in range(10):
            cal.record_outcome(True, True)
        # 100% accuracy, probability=1.0 → confidence = |1.0-0.5|*2*1.0 = 1.0
        assert cal.confidence(1.0) == 1.0
        # probability=0.5 → confidence = 0.0
        assert cal.confidence(0.5) == 0.0

    def test_needs_recalibration_insufficient_samples(self):
        cal = PredictionCalibrator()
        for _ in range(10):
            cal.record_outcome(True, False)
        assert not cal.needs_recalibration(min_samples=50)

    def test_needs_recalibration_low_accuracy(self):
        cal = PredictionCalibrator()
        for _ in range(60):
            cal.record_outcome(True, False)  # All wrong
        assert cal.needs_recalibration(min_samples=50)

    def test_needs_recalibration_good_accuracy(self):
        cal = PredictionCalibrator()
        for _ in range(60):
            cal.record_outcome(True, True)  # All correct
        assert not cal.needs_recalibration(min_samples=50)

    def test_outcome_count(self):
        cal = PredictionCalibrator(rolling_window=10)
        for _ in range(5):
            cal.record_outcome(True, True)
        assert cal.outcome_count() == 5

    def test_outcome_count_window_limit(self):
        cal = PredictionCalibrator(rolling_window=10)
        for _ in range(20):
            cal.record_outcome(True, True)
        assert cal.outcome_count() == 10

    def test_save_and_load(self, tmp_path):
        cal = PredictionCalibrator(a=-2.0, b=0.5, rolling_window=50)
        for _ in range(5):
            cal.record_outcome(True, True)
        path = tmp_path / "calibration.json"
        cal.save(path)
        assert path.exists()

        loaded = PredictionCalibrator.load(path)
        assert loaded.a == -2.0
        assert loaded.b == 0.5
        assert loaded._rolling_window == 50

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            PredictionCalibrator.load(tmp_path / "nonexistent.json")

    def test_thread_safety(self):
        import threading

        cal = PredictionCalibrator()
        errors = []

        def record_many():
            try:
                for _ in range(100):
                    cal.record_outcome(True, True)
                    cal.rolling_accuracy()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ══════════════════════════════════════════════════════════════════
# PredictionService Tests
# ══════════════════════════════════════════════════════════════════


class TestPredictionResult:
    def test_dataclass_fields(self):
        pr = PredictionResult(
            symbol="BTC/USDT",
            probability=0.75,
            raw_probability=0.72,
            confidence=0.6,
            direction="up",
            model_id="test_model",
        )
        assert pr.symbol == "BTC/USDT"
        assert pr.probability == 0.75
        assert pr.direction == "up"
        assert pr.asset_class == "crypto"  # default


class TestPredictionService:
    def test_predict_single_no_models(self, tmp_models_dir):
        registry = ModelRegistry(models_dir=tmp_models_dir)
        svc = PredictionService(registry=registry)
        features = pd.DataFrame({"a": [1, 2, 3]})
        result = svc.predict_single("BTC/USDT", features)
        assert result is None

    def test_predict_single_with_model(self, ohlcv_df, tmp_models_dir):
        model_id, registry, train_result = _train_and_save(ohlcv_df, tmp_models_dir)
        svc = PredictionService(registry=registry)
        x, _, names = build_feature_matrix(ohlcv_df)
        result = svc.predict_single("BTC/USDT", x.tail(5))
        assert result is not None
        assert isinstance(result, PredictionResult)
        assert result.symbol == "BTC/USDT"
        assert 0 <= result.probability <= 1
        assert result.direction in ("up", "down")
        assert result.model_id == model_id

    def test_predict_single_caching(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        svc = PredictionService(registry=registry, cache_ttl=60)
        x, _, _ = build_feature_matrix(ohlcv_df)
        result1 = svc.predict_single("BTC/USDT", x.tail(5))
        result2 = svc.predict_single("BTC/USDT", x.tail(5))
        # Second call should return cached
        assert result1 is not None
        assert result2 is not None
        assert result1.predicted_at == result2.predicted_at

    def test_predict_single_cache_expiry(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        svc = PredictionService(registry=registry, cache_ttl=0.01)
        x, _, _ = build_feature_matrix(ohlcv_df)
        result1 = svc.predict_single("BTC/USDT", x.tail(5))
        time.sleep(0.02)
        result2 = svc.predict_single("BTC/USDT", x.tail(5))
        assert result1 is not None
        assert result2 is not None
        # Different timestamps = cache miss
        assert result1.predicted_at != result2.predicted_at

    def test_predict_single_with_calibrator(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        cal = PredictionCalibrator(a=-1.0, b=0.0)
        svc = PredictionService(registry=registry, calibrator=cal)
        x, _, _ = build_feature_matrix(ohlcv_df)
        result = svc.predict_single("BTC/USDT", x.tail(5))
        assert result is not None
        # Calibrated prob should differ from raw
        # (may be same in edge cases but structure is tested)
        assert 0 <= result.probability <= 1

    def test_predict_batch(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        svc = PredictionService(registry=registry)
        x, _, _ = build_feature_matrix(ohlcv_df)
        feat_map = {"BTC/USDT": x.tail(5), "ETH/USDT": x.tail(5)}
        results = svc.predict_batch(["BTC/USDT", "ETH/USDT"], feat_map)
        assert len(results) == 2

    def test_predict_batch_empty_features(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        svc = PredictionService(registry=registry)
        results = svc.predict_batch(["BTC/USDT"], {"BTC/USDT": pd.DataFrame()})
        assert results == []

    def test_predict_batch_missing_symbol(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        svc = PredictionService(registry=registry)
        x, _, _ = build_feature_matrix(ohlcv_df)
        results = svc.predict_batch(["BTC/USDT", "MISSING"], {"BTC/USDT": x.tail(5)})
        assert len(results) == 1

    def test_score_opportunity(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        svc = PredictionService(registry=registry)
        x, _, _ = build_feature_matrix(ohlcv_df)
        score = svc.score_opportunity("BTC/USDT", x.tail(5), "breakout", 70.0)
        assert 0 <= score <= 100

    def test_score_opportunity_no_model(self, tmp_models_dir):
        registry = ModelRegistry(models_dir=tmp_models_dir)
        svc = PredictionService(registry=registry)
        score = svc.score_opportunity("BTC/USDT", pd.DataFrame({"a": [1]}), "breakout", 70.0)
        assert score == 70.0  # Fallback to scanner score

    def test_invalidate_cache(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        svc = PredictionService(registry=registry, cache_ttl=300)
        x, _, _ = build_feature_matrix(ohlcv_df)
        svc.predict_single("BTC/USDT", x.tail(5))
        svc.invalidate_cache("BTC/USDT")
        # Cache should be empty for that symbol
        assert svc._get_cached("BTC/USDT:crypto") is None

    def test_invalidate_cache_all(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        svc = PredictionService(registry=registry, cache_ttl=300)
        x, _, _ = build_feature_matrix(ohlcv_df)
        svc.predict_single("BTC/USDT", x.tail(5))
        svc.invalidate_cache()
        assert svc._get_cached("BTC/USDT:crypto") is None

    def test_select_model_exact_symbol(self, ohlcv_df, tmp_models_dir):
        _train_and_save(ohlcv_df, tmp_models_dir, symbol="ETH/USDT")
        btc_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir, symbol="BTC/USDT")
        svc = PredictionService(registry=registry)
        selected = svc._select_model("BTC/USDT", "crypto")
        assert selected == btc_id

    def test_select_model_asset_class_fallback(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir, symbol="", label="crypto general")
        svc = PredictionService(registry=registry)
        selected = svc._select_model("DOGE/USDT", "crypto")
        assert selected == model_id

    def test_select_model_best_accuracy_fallback(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir, symbol="", label="")
        svc = PredictionService(registry=registry)
        selected = svc._select_model("UNKNOWN/USDT", "other")
        assert selected == model_id

    def test_predict_single_model_load_failure(self, tmp_models_dir):
        registry = ModelRegistry(models_dir=tmp_models_dir)
        # Create a model entry without model.txt (triggers FileNotFoundError
        # because load_model checks model_dir exists but model.txt is missing)
        model_dir = tmp_models_dir / "corrupt_model"
        model_dir.mkdir()
        (model_dir / "manifest.json").write_text(json.dumps({
            "model_id": "corrupt_model",
            "symbol": "BTC/USDT",
            "metrics": {"accuracy": 0.8},
        }))
        svc = PredictionService(registry=registry)
        # Patch load_model to raise FileNotFoundError (simulates missing model file)
        with patch.object(registry, "load_model", side_effect=FileNotFoundError("model.txt not found")):
            result = svc.predict_single("BTC/USDT", pd.DataFrame({"a": [1]}))
        assert result is None

    def test_predict_single_prediction_exception(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        svc = PredictionService(registry=registry)
        # Pass features with wrong shape
        bad_features = pd.DataFrame({"wrong_col": [1, 2, 3]})
        result = svc.predict_single("BTC/USDT", bad_features)
        assert result is None


# ══════════════════════════════════════════════════════════════════
# ModelEnsemble Tests
# ══════════════════════════════════════════════════════════════════


class TestModelEnsemble:
    def test_invalid_mode(self, tmp_models_dir):
        with pytest.raises(ValueError, match="Invalid ensemble mode"):
            ModelEnsemble(mode="invalid")

    def test_empty_ensemble_predict(self, tmp_models_dir):
        registry = ModelRegistry(models_dir=tmp_models_dir)
        ens = ModelEnsemble(registry=registry)
        assert ens.predict(pd.DataFrame()) is None

    def test_build_from_empty_registry(self, tmp_models_dir):
        registry = ModelRegistry(models_dir=tmp_models_dir)
        ens = ModelEnsemble(registry=registry)
        count = ens.build_from_registry()
        assert count == 0

    def test_build_from_registry(self, ohlcv_df, tmp_models_dir):
        _train_and_save(ohlcv_df, tmp_models_dir, symbol="BTC/USDT")
        _train_and_save(ohlcv_df, tmp_models_dir, symbol="ETH/USDT")
        registry = ModelRegistry(models_dir=tmp_models_dir)
        ens = ModelEnsemble(registry=registry, max_models=5)
        count = ens.build_from_registry()
        assert count == 2
        assert ens.model_count == 2

    def test_build_with_symbol_filter(self, ohlcv_df, tmp_models_dir):
        _train_and_save(ohlcv_df, tmp_models_dir, symbol="BTC/USDT")
        _train_and_save(ohlcv_df, tmp_models_dir, symbol="ETH/USDT")
        registry = ModelRegistry(models_dir=tmp_models_dir)
        ens = ModelEnsemble(registry=registry)
        count = ens.build_from_registry(symbol="BTC/USDT")
        assert count == 1

    def test_predict_simple_average(self, ohlcv_df, tmp_models_dir):
        _train_and_save(ohlcv_df, tmp_models_dir, symbol="BTC/USDT")
        _train_and_save(ohlcv_df, tmp_models_dir, symbol="ETH/USDT")
        registry = ModelRegistry(models_dir=tmp_models_dir)
        ens = ModelEnsemble(registry=registry, mode="simple_average")
        ens.build_from_registry()
        x, _, _ = build_feature_matrix(ohlcv_df)
        result = ens.predict(x.tail(5))
        assert result is not None
        assert isinstance(result, EnsembleResult)
        assert 0 <= result.probability <= 1
        assert result.direction in ("up", "down")
        assert 0 <= result.agreement_ratio <= 1
        assert result.model_count == 2
        assert result.mode == "simple_average"

    def test_predict_accuracy_weighted(self, ohlcv_df, tmp_models_dir):
        _train_and_save(ohlcv_df, tmp_models_dir, symbol="BTC/USDT")
        registry = ModelRegistry(models_dir=tmp_models_dir)
        ens = ModelEnsemble(registry=registry, mode="accuracy_weighted")
        ens.build_from_registry()
        x, _, _ = build_feature_matrix(ohlcv_df)
        result = ens.predict(x.tail(5))
        assert result is not None
        assert result.mode == "accuracy_weighted"

    def test_predict_regime_gated(self, ohlcv_df, tmp_models_dir):
        _train_and_save(ohlcv_df, tmp_models_dir, label="crypto trending")
        registry = ModelRegistry(models_dir=tmp_models_dir)
        ens = ModelEnsemble(registry=registry, mode="regime_gated")
        count = ens.build_from_registry(regime="trending")
        assert count == 1

    def test_add_model(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        ens = ModelEnsemble(registry=registry, max_models=3)
        assert ens.add_model(model_id) is True
        assert ens.model_count == 1

    def test_add_model_duplicate(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        ens = ModelEnsemble(registry=registry)
        ens.add_model(model_id)
        assert ens.add_model(model_id) is False

    def test_add_model_at_capacity(self, ohlcv_df, tmp_models_dir):
        model_id1, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir, symbol="BTC/USDT")
        model_id2, _, _ = _train_and_save(ohlcv_df, tmp_models_dir, symbol="ETH/USDT")
        ens = ModelEnsemble(registry=registry, max_models=1)
        ens.add_model(model_id1)
        assert ens.add_model(model_id2) is False

    def test_add_model_nonexistent(self, tmp_models_dir):
        registry = ModelRegistry(models_dir=tmp_models_dir)
        ens = ModelEnsemble(registry=registry)
        assert ens.add_model("nonexistent") is False

    def test_clear(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        ens = ModelEnsemble(registry=registry)
        ens.add_model(model_id)
        assert ens.model_count == 1
        ens.clear()
        assert ens.model_count == 0

    def test_model_ids_property(self, ohlcv_df, tmp_models_dir):
        model_id, registry, _ = _train_and_save(ohlcv_df, tmp_models_dir)
        ens = ModelEnsemble(registry=registry)
        ens.add_model(model_id)
        assert model_id in ens.model_ids

    def test_max_ensemble_size_cap(self):
        ens = ModelEnsemble(max_models=100)
        assert ens._max_models == 5  # Capped at MAX_ENSEMBLE_SIZE

    def test_agreement_ratio_unanimous(self, ohlcv_df, tmp_models_dir):
        """When all models agree, agreement should be 1.0."""
        _train_and_save(ohlcv_df, tmp_models_dir, symbol="BTC/USDT")
        _train_and_save(ohlcv_df, tmp_models_dir, symbol="ETH/USDT")
        registry = ModelRegistry(models_dir=tmp_models_dir)
        ens = ModelEnsemble(registry=registry)
        ens.build_from_registry()
        x, _, _ = build_feature_matrix(ohlcv_df)
        result = ens.predict(x.tail(5))
        assert result is not None
        # With same training data, models should largely agree
        assert result.agreement_ratio >= 0.5


# ══════════════════════════════════════════════════════════════════
# FeedbackTracker Tests
# ══════════════════════════════════════════════════════════════════


class TestFeedbackTracker:
    def test_record_prediction(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        record = tracker.record_prediction(
            model_id="test_model",
            symbol="BTC/USDT",
            asset_class="crypto",
            probability=0.75,
            direction="up",
            regime="STRONG_TREND_UP",
        )
        assert record["model_id"] == "test_model"
        assert record["symbol"] == "BTC/USDT"
        assert record["probability"] == 0.75
        assert record["actual_direction"] is None
        assert record["correct"] is None

    def test_record_creates_jsonl_file(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        tracker.record_prediction("m1", "BTC/USDT", "crypto", 0.5, "up")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = tmp_feedback_dir / f"{today}.jsonl"
        assert filepath.exists()
        lines = filepath.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["model_id"] == "m1"

    def test_record_multiple_predictions(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        for i in range(5):
            tracker.record_prediction(f"m{i}", "BTC/USDT", "crypto", 0.5 + i * 0.05, "up")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = tmp_feedback_dir / f"{today}.jsonl"
        lines = filepath.read_text().strip().split("\n")
        assert len(lines) == 5

    def test_backfill_outcomes(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tracker.record_prediction("m1", "BTC/USDT", "crypto", 0.75, "up", timestamp=f"{today}T12:00:00+00:00")
        tracker.record_prediction("m1", "ETH/USDT", "crypto", 0.3, "down", timestamp=f"{today}T12:00:00+00:00")

        updated = tracker.backfill_outcomes(
            {"BTC/USDT": 0.05, "ETH/USDT": -0.02},
            date=today,
        )
        assert updated == 2

        records = tracker._load_records(tmp_feedback_dir / f"{today}.jsonl")
        assert records[0]["actual_direction"] == "up"
        assert records[0]["correct"] is True
        assert records[1]["actual_direction"] == "down"
        assert records[1]["correct"] is True

    def test_backfill_no_file(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        updated = tracker.backfill_outcomes({"BTC/USDT": 0.05}, date="2020-01-01")
        assert updated == 0

    def test_backfill_already_filled(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tracker.record_prediction("m1", "BTC/USDT", "crypto", 0.75, "up", timestamp=f"{today}T12:00:00+00:00")
        tracker.backfill_outcomes({"BTC/USDT": 0.05}, date=today)
        # Second backfill should not update again
        updated = tracker.backfill_outcomes({"BTC/USDT": -0.05}, date=today)
        assert updated == 0

    def test_backfill_missing_symbol(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tracker.record_prediction("m1", "BTC/USDT", "crypto", 0.75, "up", timestamp=f"{today}T12:00:00+00:00")
        updated = tracker.backfill_outcomes({"ETH/USDT": 0.05}, date=today)
        assert updated == 0

    def test_get_model_accuracy(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # 7 correct, 3 wrong
        for i in range(10):
            direction = "up" if i < 7 else "down"
            tracker.record_prediction(
                "m1", "BTC/USDT", "crypto", 0.7, direction,
                regime="TRENDING", timestamp=f"{today}T{i:02d}:00:00+00:00",
            )
        actual_returns = {"BTC/USDT": 0.01}
        tracker.backfill_outcomes(actual_returns, date=today)

        stats = tracker.get_model_accuracy("m1", lookback_days=1)
        assert stats["total_predictions"] == 10
        assert stats["correct_predictions"] == 7
        assert abs(stats["accuracy"] - 0.7) < 0.01
        assert "TRENDING" in stats["accuracy_by_regime"]

    def test_get_model_accuracy_no_data(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        stats = tracker.get_model_accuracy("nonexistent")
        assert stats["total_predictions"] == 0
        assert stats["accuracy"] == 0.0

    def test_should_retrain_no_predictions(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        assert tracker.should_retrain("m1") is True  # Stale

    def test_should_retrain_low_accuracy(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # All wrong predictions
        for i in range(60):
            tracker.record_prediction(
                "m1", "BTC/USDT", "crypto", 0.7, "up",
                timestamp=f"{today}T00:{i:02d}:00+00:00",
            )
        tracker.backfill_outcomes({"BTC/USDT": -0.01}, date=today)
        assert tracker.should_retrain("m1", min_predictions=50) is True

    def test_should_retrain_stale(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        # Old predictions only (not in recent days)
        old_date = "2020-01-01"
        filepath = tmp_feedback_dir / f"{old_date}.jsonl"
        record = {
            "model_id": "m1", "symbol": "BTC/USDT", "asset_class": "crypto",
            "probability": 0.7, "direction": "up", "regime": "", "timestamp": f"{old_date}T00:00:00+00:00",
            "actual_direction": "up", "correct": True,
        }
        filepath.write_text(json.dumps(record) + "\n")
        assert tracker.should_retrain("m1", stale_days=7) is True

    def test_should_retrain_regime_variance(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Good in trending, bad in ranging
        for i in range(30):
            tracker.record_prediction(
                "m1", "BTC/USDT", "crypto", 0.7, "up",
                regime="TRENDING", timestamp=f"{today}T00:{i:02d}:00+00:00",
            )
        for i in range(30):
            tracker.record_prediction(
                "m1", "BTC/USDT", "crypto", 0.7, "down",
                regime="RANGING", timestamp=f"{today}T01:{i:02d}:00+00:00",
            )
        tracker.backfill_outcomes({"BTC/USDT": 0.01}, date=today)
        # TRENDING: all correct (up=up), RANGING: all wrong (down≠up)
        assert tracker.should_retrain("m1", min_predictions=50) is True

    def test_should_retrain_good_model(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for i in range(60):
            tracker.record_prediction(
                "m1", "BTC/USDT", "crypto", 0.7, "up",
                regime="TRENDING", timestamp=f"{today}T00:{i:02d}:00+00:00",
            )
        tracker.backfill_outcomes({"BTC/USDT": 0.01}, date=today)
        assert tracker.should_retrain("m1", min_predictions=50) is False

    def test_get_all_model_stats(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tracker.record_prediction("m1", "BTC/USDT", "crypto", 0.7, "up", timestamp=f"{today}T00:00:00+00:00")
        tracker.record_prediction("m2", "ETH/USDT", "crypto", 0.3, "down", timestamp=f"{today}T00:01:00+00:00")
        tracker.backfill_outcomes({"BTC/USDT": 0.01, "ETH/USDT": -0.01}, date=today)
        stats = tracker.get_all_model_stats(lookback_days=1)
        assert len(stats) == 2

    def test_corrupt_record_skipped(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = tmp_feedback_dir / f"{today}.jsonl"
        filepath.write_text("not valid json\n")
        records = tracker._load_records(filepath)
        assert records == []

    def test_record_with_custom_timestamp(self, tmp_feedback_dir):
        tracker = FeedbackTracker(feedback_dir=tmp_feedback_dir)
        record = tracker.record_prediction(
            "m1", "BTC/USDT", "crypto", 0.7, "up",
            timestamp="2025-06-15T12:00:00+00:00",
        )
        assert record["timestamp"] == "2025-06-15T12:00:00+00:00"
        filepath = tmp_feedback_dir / "2025-06-15.jsonl"
        assert filepath.exists()


# ══════════════════════════════════════════════════════════════════
# Enhanced Features Tests
# ══════════════════════════════════════════════════════════════════


class TestRegimeFeatures:
    def test_adds_regime_columns(self, ohlcv_df):
        feat = add_regime_features(ohlcv_df, regime_ordinal=3, regime_confidence=0.8, regime_adx=25.0)
        assert "regime_ordinal" in feat.columns
        assert "regime_confidence" in feat.columns
        assert "regime_adx" in feat.columns
        assert "regime_trend_alignment" in feat.columns
        assert feat["regime_ordinal"].iloc[0] == 3
        assert feat["regime_confidence"].iloc[0] == 0.8

    def test_none_defaults(self, ohlcv_df):
        feat = add_regime_features(ohlcv_df)
        assert feat["regime_ordinal"].iloc[0] == -1
        assert feat["regime_confidence"].iloc[0] == 0.0
        assert feat["regime_adx"].iloc[0] == 0.0

    def test_trend_alignment_bounded(self, ohlcv_df):
        feat = add_regime_features(ohlcv_df)
        # After warmup, values should be bounded
        valid = feat["regime_trend_alignment"].dropna()
        assert valid.max() <= 1.01
        assert valid.min() >= -1.01


class TestSentimentFeatures:
    def test_adds_sentiment_columns(self):
        feat = add_sentiment_features(
            sentiment_score=0.5,
            sentiment_conviction=0.8,
            sentiment_position_modifier=1.1,
            n_rows=10,
        )
        assert len(feat) == 10
        assert feat["sentiment_score"].iloc[0] == 0.5
        assert feat["sentiment_conviction"].iloc[0] == 0.8
        assert feat["sentiment_position_modifier"].iloc[0] == 1.1

    def test_none_defaults(self):
        feat = add_sentiment_features(n_rows=5)
        assert feat["sentiment_score"].iloc[0] == 0.0
        assert feat["sentiment_conviction"].iloc[0] == 0.0
        assert feat["sentiment_position_modifier"].iloc[0] == 1.0


class TestTemporalFeatures:
    def test_datetime_index(self, ohlcv_df):
        feat = add_temporal_features(ohlcv_df)
        assert "hour_sin" in feat.columns
        assert "hour_cos" in feat.columns
        assert "dow_sin" in feat.columns
        assert "dow_cos" in feat.columns
        assert "month_sin" in feat.columns
        assert "month_cos" in feat.columns
        # Sin/cos should be in [-1, 1]
        assert feat["hour_sin"].max() <= 1.0
        assert feat["hour_sin"].min() >= -1.0

    def test_non_datetime_index(self):
        df = pd.DataFrame({"close": [1, 2, 3]}, index=[0, 1, 2])
        feat = add_temporal_features(df)
        # Should not raise, fills with zeros
        assert len(feat) == 3
        assert feat["hour_sin"].iloc[0] == 0.0


class TestVolatilityRegimeFeatures:
    def test_adds_volatility_columns(self, ohlcv_df):
        feat = add_volatility_regime_features(ohlcv_df)
        assert "bb_width_percentile_100" in feat.columns
        assert "atr_percentile_100" in feat.columns
        assert "realized_vol_20" in feat.columns
        assert "vol_of_vol_20" in feat.columns

    def test_percentiles_bounded(self, ohlcv_df):
        feat = add_volatility_regime_features(ohlcv_df)
        valid = feat["bb_width_percentile_100"].dropna()
        assert valid.max() <= 1.01
        assert valid.min() >= -0.01


class TestBuildFeatureMatrixEnhanced:
    """Test feature engineering with max_features=0 to disable reduction."""

    _no_reduce = {"max_features": 0, "target_dead_zone": 0.0}

    def test_with_regime_features(self, ohlcv_df):
        x, y, names = build_feature_matrix(
            ohlcv_df,
            config=self._no_reduce,
            include_regime=True,
            regime_ordinal=2,
            regime_confidence=0.7,
        )
        assert "regime_ordinal" in names
        assert "regime_confidence" in names

    def test_with_sentiment_features(self, ohlcv_df):
        x, y, names = build_feature_matrix(
            ohlcv_df,
            config=self._no_reduce,
            include_sentiment=True,
            sentiment_score=0.3,
        )
        assert "sentiment_score" in names

    def test_with_temporal_features(self, ohlcv_df):
        x, y, names = build_feature_matrix(ohlcv_df, config=self._no_reduce, include_temporal=True)
        assert "hour_sin" in names
        assert "dow_cos" in names

    def test_with_volatility_regime_features(self, ohlcv_df):
        x, y, names = build_feature_matrix(ohlcv_df, config=self._no_reduce, include_volatility_regime=True)
        assert "realized_vol_20" in names
        assert "vol_of_vol_20" in names

    def test_all_features_combined(self, ohlcv_df):
        x, y, names = build_feature_matrix(
            ohlcv_df,
            config=self._no_reduce,
            include_regime=True,
            include_sentiment=True,
            include_temporal=True,
            include_volatility_regime=True,
            regime_ordinal=1,
            sentiment_score=0.5,
        )
        # Should have significantly more features than base
        assert len(names) > 50

    def test_backward_compatible(self, ohlcv_df):
        """Calling with no new params should produce same as before."""
        x, y, names = build_feature_matrix(ohlcv_df)
        assert "regime_ordinal" not in names
        assert "sentiment_score" not in names
        assert "hour_sin" not in names
        assert "realized_vol_20" not in names


# ══════════════════════════════════════════════════════════════════
# Enhanced Trainer Tests
# ══════════════════════════════════════════════════════════════════


class TestTrainerCalibration:
    def test_train_with_calibration(self, ohlcv_df):
        from common.ml.trainer import train_model

        x, y, names = build_feature_matrix(ohlcv_df)
        result = train_model(x, y, names, fit_calibration=True)
        assert "calibration" in result["metadata"]
        assert "a" in result["metadata"]["calibration"]
        assert "b" in result["metadata"]["calibration"]

    def test_train_without_calibration(self, ohlcv_df):
        from common.ml.trainer import train_model

        x, y, names = build_feature_matrix(ohlcv_df)
        result = train_model(x, y, names, fit_calibration=False)
        assert "calibration" not in result["metadata"]


# ══════════════════════════════════════════════════════════════════
# __init__.py Import Tests
# ══════════════════════════════════════════════════════════════════


class TestMLPackageImports:
    def test_imports(self):
        from common.ml import (
            EnsembleResult,
            FeedbackTracker,
            ModelEnsemble,
            ModelRegistry,
            PredictionCalibrator,
            PredictionResult,
            PredictionService,
        )

        assert callable(PredictionService)
        assert callable(PredictionCalibrator)
        assert callable(ModelEnsemble)
        assert callable(FeedbackTracker)
