"""Tests for Phase 4: Signal Service, API endpoints, ML models, and task executors.

Covers:
- SignalService (get_signal, get_signals_batch, get_entry_recommendation)
- MLPrediction / MLModelPerformance models
- Signal API views (detail, batch, entry-check, strategy-status)
- ML tracking views (prediction list, model performance)
- Task executors (ml_predict, ml_feedback, ml_retrain, conviction_audit, strategy_orchestration)
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from rest_framework.test import APIClient

from analysis.models import BackgroundJob, BacktestResult, MLModelPerformance, MLPrediction

# ══════════════════════════════════════════════════════
# MLPrediction model tests
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMLPredictionModel:
    def test_create_prediction(self):
        pred = MLPrediction.objects.create(
            model_id="test_model_1",
            symbol="BTC/USDT",
            asset_class="crypto",
            probability=0.75,
            confidence=0.8,
            direction="up",
            regime="STRONG_TREND_UP",
        )
        assert pred.prediction_id
        assert pred.probability == 0.75
        assert pred.direction == "up"
        assert pred.correct is None
        assert pred.actual_direction is None

    def test_str_representation(self):
        pred = MLPrediction(
            model_id="m1",
            symbol="ETH/USDT",
            probability=0.65,
            direction="down",
        )
        assert "ETH/USDT" in str(pred)
        assert "down" in str(pred)
        assert "0.65" in str(pred)

    def test_clean_valid(self):
        pred = MLPrediction(
            model_id="m1",
            symbol="BTC/USDT",
            probability=0.5,
            confidence=0.5,
            direction="up",
        )
        pred.clean()  # Should not raise

    def test_clean_invalid_probability(self):
        from django.core.exceptions import ValidationError

        pred = MLPrediction(
            model_id="m1",
            symbol="BTC/USDT",
            probability=1.5,
            confidence=0.5,
            direction="up",
        )
        with pytest.raises(ValidationError) as exc_info:
            pred.clean()
        assert "probability" in exc_info.value.message_dict

    def test_clean_invalid_confidence(self):
        from django.core.exceptions import ValidationError

        pred = MLPrediction(
            model_id="m1",
            symbol="BTC/USDT",
            probability=0.5,
            confidence=-0.1,
            direction="up",
        )
        with pytest.raises(ValidationError) as exc_info:
            pred.clean()
        assert "confidence" in exc_info.value.message_dict

    def test_ordering(self):
        MLPrediction.objects.create(
            model_id="m1",
            symbol="BTC/USDT",
            probability=0.5,
            confidence=0.5,
            direction="up",
        )
        MLPrediction.objects.create(
            model_id="m1",
            symbol="ETH/USDT",
            probability=0.6,
            confidence=0.5,
            direction="up",
        )
        preds = list(MLPrediction.objects.all())
        assert preds[0].predicted_at >= preds[1].predicted_at

    def test_fill_outcome(self):
        pred = MLPrediction.objects.create(
            model_id="m1",
            symbol="BTC/USDT",
            probability=0.7,
            confidence=0.5,
            direction="up",
        )
        pred.actual_direction = "up"
        pred.correct = True
        pred.save()
        pred.refresh_from_db()
        assert pred.correct is True
        assert pred.actual_direction == "up"


# ══════════════════════════════════════════════════════
# MLModelPerformance model tests
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMLModelPerformanceModel:
    def test_create_performance(self):
        perf = MLModelPerformance.objects.create(
            model_id="test_model_1",
            total_predictions=100,
            correct_predictions=65,
            rolling_accuracy=0.65,
            accuracy_by_regime={"STRONG_TREND_UP": 0.72, "RANGING": 0.55},
        )
        assert perf.model_id == "test_model_1"
        assert perf.rolling_accuracy == 0.65
        assert perf.retrain_recommended is False

    def test_str_representation(self):
        perf = MLModelPerformance(model_id="m1", rolling_accuracy=0.72)
        assert "m1" in str(perf)
        assert "0.72" in str(perf)

    def test_clean_valid(self):
        perf = MLModelPerformance(
            model_id="m1",
            total_predictions=10,
            rolling_accuracy=0.5,
        )
        perf.clean()

    def test_clean_invalid_accuracy(self):
        from django.core.exceptions import ValidationError

        perf = MLModelPerformance(model_id="m1", rolling_accuracy=1.5)
        with pytest.raises(ValidationError) as exc_info:
            perf.clean()
        assert "rolling_accuracy" in exc_info.value.message_dict

    def test_clean_negative_predictions(self):
        from django.core.exceptions import ValidationError

        perf = MLModelPerformance(model_id="m1", total_predictions=-1, rolling_accuracy=0.5)
        with pytest.raises(ValidationError) as exc_info:
            perf.clean()
        assert "total_predictions" in exc_info.value.message_dict

    def test_update_or_create(self):
        MLModelPerformance.objects.create(
            model_id="m1",
            total_predictions=50,
            correct_predictions=25,
            rolling_accuracy=0.5,
        )
        perf, created = MLModelPerformance.objects.update_or_create(
            model_id="m1",
            defaults={"total_predictions": 100, "correct_predictions": 60, "rolling_accuracy": 0.6},
        )
        assert not created
        assert perf.total_predictions == 100
        assert perf.rolling_accuracy == 0.6


# ══════════════════════════════════════════════════════
# SignalService tests
# ══════════════════════════════════════════════════════


class TestSignalService:
    @pytest.fixture(autouse=True)
    def _clear_signal_cache(self):
        from analysis.services.signal_service import clear_signal_cache

        clear_signal_cache()
        yield
        clear_signal_cache()

    @patch("analysis.services.signal_service.ensure_platform_imports")
    @patch("analysis.services.signal_service.SignalService._get_regime_state", return_value=None)
    @patch(
        "analysis.services.signal_service.SignalService._get_ml_prediction",
        return_value=(None, None),
    )
    @patch(
        "analysis.services.signal_service.SignalService._get_sentiment_signal",
        return_value=(None, None),
    )
    @patch("analysis.services.signal_service.SignalService._get_scanner_score", return_value=None)
    @patch("analysis.services.signal_service.SignalService._get_win_rate", return_value=None)
    def test_get_signal_no_sources(self, _wr, _scan, _sent, _ml, _regime, _imports):
        from analysis.services.signal_service import SignalService

        result = SignalService.get_signal("BTC/USDT", "crypto", "CryptoInvestorV1")
        assert "composite_score" in result
        assert "signal_label" in result
        assert "entry_approved" in result
        assert "position_modifier" in result
        assert "components" in result
        assert "reasoning" in result
        assert result["symbol"] == "BTC/USDT"
        assert result["asset_class"] == "crypto"

    @patch("analysis.services.signal_service.ensure_platform_imports")
    @patch("analysis.services.signal_service.SignalService._get_regime_state")
    @patch(
        "analysis.services.signal_service.SignalService._get_ml_prediction", return_value=(0.8, 0.9)
    )
    @patch(
        "analysis.services.signal_service.SignalService._get_sentiment_signal",
        return_value=(0.3, 0.7),
    )
    @patch("analysis.services.signal_service.SignalService._get_scanner_score", return_value=80.0)
    @patch("analysis.services.signal_service.SignalService._get_win_rate", return_value=65.0)
    def test_get_signal_all_sources(self, _wr, _scan, _sent, _ml, _regime, _imports):
        mock_state = MagicMock()
        mock_state.regime.value = "STRONG_TREND_UP"
        mock_state.confidence = 0.9
        _regime.return_value = mock_state

        from analysis.services.signal_service import SignalService

        result = SignalService.get_signal("BTC/USDT", "crypto", "CryptoInvestorV1")
        assert result["composite_score"] > 0
        assert len(result["sources_available"]) > 0

    @patch("analysis.services.signal_service.ensure_platform_imports")
    @patch("analysis.services.signal_service.SignalService._get_regime_state", return_value=None)
    @patch(
        "analysis.services.signal_service.SignalService._get_ml_prediction",
        return_value=(None, None),
    )
    @patch(
        "analysis.services.signal_service.SignalService._get_sentiment_signal",
        return_value=(None, None),
    )
    @patch("analysis.services.signal_service.SignalService._get_scanner_score", return_value=None)
    @patch("analysis.services.signal_service.SignalService._get_win_rate", return_value=None)
    def test_get_signals_batch(self, _wr, _scan, _sent, _ml, _regime, _imports):
        from analysis.services.signal_service import SignalService

        results = SignalService.get_signals_batch(
            ["BTC/USDT", "ETH/USDT"],
            "crypto",
            "CryptoInvestorV1",
        )
        assert len(results) == 2
        assert results[0]["symbol"] == "BTC/USDT"
        assert results[1]["symbol"] == "ETH/USDT"

    @patch("analysis.services.signal_service.ensure_platform_imports")
    @patch("analysis.services.signal_service.SignalService._get_regime_state", return_value=None)
    @patch(
        "analysis.services.signal_service.SignalService._get_ml_prediction",
        return_value=(None, None),
    )
    @patch(
        "analysis.services.signal_service.SignalService._get_sentiment_signal",
        return_value=(None, None),
    )
    @patch("analysis.services.signal_service.SignalService._get_scanner_score", return_value=None)
    @patch("analysis.services.signal_service.SignalService._get_win_rate", return_value=None)
    def test_get_entry_recommendation(self, _wr, _scan, _sent, _ml, _regime, _imports):
        from analysis.services.signal_service import SignalService

        rec = SignalService.get_entry_recommendation("BTC/USDT", "CryptoInvestorV1", "crypto")
        assert "approved" in rec
        assert "score" in rec
        assert "position_modifier" in rec
        assert "reasoning" in rec
        assert "signal_label" in rec

    @patch("analysis.services.signal_service.ensure_platform_imports")
    @patch("analysis.services.signal_service.SignalService._get_regime_state", return_value=None)
    @patch(
        "analysis.services.signal_service.SignalService._get_ml_prediction",
        return_value=(None, None),
    )
    @patch(
        "analysis.services.signal_service.SignalService._get_sentiment_signal",
        return_value=(None, None),
    )
    @patch("analysis.services.signal_service.SignalService._get_scanner_score", return_value=None)
    @patch("analysis.services.signal_service.SignalService._get_win_rate", return_value=None)
    def test_batch_caps_at_50(self, _wr, _scan, _sent, _ml, _regime, _imports):
        from analysis.services.signal_service import SignalService

        symbols = [f"SYM{i}/USDT" for i in range(60)]
        results = SignalService.get_signals_batch(symbols, "crypto")
        assert len(results) == 50

    @patch("analysis.services.signal_service.ensure_platform_imports")
    def test_get_regime_state_exception_returns_none(self, _imports):
        _imports.side_effect = ImportError("no module")
        from analysis.services.signal_service import SignalService

        result = SignalService._get_regime_state("BTC/USDT", "crypto")
        assert result is None

    def test_get_ml_prediction_exception_returns_nones(self):
        with patch(
            "analysis.services.signal_service.ensure_platform_imports", side_effect=ImportError
        ):
            from analysis.services.signal_service import SignalService

            prob, conf = SignalService._get_ml_prediction("BTC/USDT", "crypto")
            assert prob is None
            assert conf is None

    def test_get_sentiment_signal_exception_returns_nones(self):
        with patch(
            "analysis.services.signal_service.ensure_platform_imports", side_effect=ImportError
        ):
            from analysis.services.signal_service import SignalService

            score, conv = SignalService._get_sentiment_signal("BTC/USDT", "crypto")
            assert score is None
            assert conv is None

    @pytest.mark.django_db
    def test_get_scanner_score_no_opportunity(self):
        from analysis.services.signal_service import SignalService

        result = SignalService._get_scanner_score("BTC/USDT", "crypto")
        assert result is None

    @pytest.mark.django_db
    def test_get_win_rate_no_backtest(self):
        from analysis.services.signal_service import SignalService

        result = SignalService._get_win_rate("CryptoInvestorV1")
        assert result is None

    @pytest.mark.django_db
    def test_get_win_rate_with_backtest(self):
        from analysis.services.signal_service import SignalService

        job = BackgroundJob.objects.create(job_type="backtest", status="completed")
        BacktestResult.objects.create(
            job=job,
            framework="freqtrade",
            strategy_name="CryptoInvestorV1",
            symbol="BTC/USDT",
            timeframe="1h",
            metrics={"win_rate": 62.5},
        )
        result = SignalService._get_win_rate("CryptoInvestorV1")
        assert result == 62.5


# ══════════════════════════════════════════════════════
# API View tests
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSignalAPIViews:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from django.contrib.auth.models import User

        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_authenticate(user=self.user)

    @patch("analysis.services.signal_service.SignalService.get_signal")
    def test_signal_detail_view(self, mock_get):
        mock_get.return_value = {
            "symbol": "BTC/USDT",
            "asset_class": "crypto",
            "timestamp": "2026-03-10T12:00:00+00:00",
            "composite_score": 72.5,
            "signal_label": "buy",
            "entry_approved": True,
            "position_modifier": 0.7,
            "hard_disabled": False,
            "components": {
                "technical": 80,
                "regime": 70,
                "ml": 65,
                "sentiment": 60,
                "scanner": 0,
                "win_rate": 50,
            },
            "confidences": {"ml": 0.8, "sentiment": 0.6, "regime": 0.9},
            "sources_available": ["regime", "ml"],
            "reasoning": ["Score: 72.5"],
        }
        resp = self.client.get(
            "/api/signals/BTC-USDT/", {"asset_class": "crypto", "strategy": "CryptoInvestorV1"}
        )
        assert resp.status_code == 200
        assert resp.data["composite_score"] == 72.5
        mock_get.assert_called_once_with("BTC/USDT", "crypto", "CryptoInvestorV1")

    @patch(
        "analysis.services.signal_service.SignalService.get_signal", side_effect=Exception("fail")
    )
    def test_signal_detail_view_error(self, mock_get):
        resp = self.client.get("/api/signals/BTC-USDT/")
        assert resp.status_code == 500
        assert "error" in resp.data

    @patch("analysis.services.signal_service.SignalService.get_signals_batch")
    def test_signal_batch_view(self, mock_batch):
        mock_batch.return_value = [
            {"symbol": "BTC/USDT", "composite_score": 70},
            {"symbol": "ETH/USDT", "composite_score": 55},
        ]
        resp = self.client.post(
            "/api/signals/batch/",
            {"symbols": ["BTC/USDT", "ETH/USDT"], "asset_class": "crypto"},
            format="json",
        )
        assert resp.status_code == 200
        assert len(resp.data) == 2

    def test_signal_batch_view_invalid(self):
        resp = self.client.post(
            "/api/signals/batch/",
            {"symbols": [], "asset_class": "crypto"},
            format="json",
        )
        assert resp.status_code == 400

    @patch("analysis.services.signal_service.SignalService.get_entry_recommendation")
    def test_entry_check_view(self, mock_rec):
        mock_rec.return_value = {
            "approved": True,
            "score": 72.5,
            "position_modifier": 0.7,
            "reasoning": ["Score above threshold"],
            "signal_label": "buy",
            "hard_disabled": False,
        }
        # Entry check is unauthenticated
        client = APIClient()
        resp = client.post(
            "/api/signals/BTC-USDT/entry-check/",
            {"strategy": "CryptoInvestorV1", "asset_class": "crypto"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["approved"] is True
        assert resp.data["score"] == 72.5

    @patch(
        "analysis.services.signal_service.SignalService.get_entry_recommendation",
        side_effect=Exception("boom"),
    )
    def test_entry_check_fail_open(self, mock_rec):
        client = APIClient()
        resp = client.post(
            "/api/signals/BTC-USDT/entry-check/",
            {"strategy": "CryptoInvestorV1"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["approved"] is True  # Fail-open

    def test_strategy_status_view(self):
        mock_state = MagicMock()
        mock_state.regime.value = "STRONG_TREND_UP"

        mock_detector_cls = MagicMock()
        mock_detector_cls.return_value.detect.return_value = mock_state

        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch.dict(
                "sys.modules",
                {
                    "common.regime.regime_detector": MagicMock(RegimeDetector=mock_detector_cls),
                    "common.signals.constants": MagicMock(
                        ALIGNMENT_TABLES={
                            "crypto": {
                                mock_state.regime: {
                                    "CryptoInvestorV1": 95,
                                    "BollingerMeanReversion": 30,
                                    "VolatilityBreakout": 60,
                                }
                            },
                        }
                    ),
                },
            ),
        ):
            resp = self.client.get("/api/signals/strategy-status/", {"asset_class": "crypto"})
            assert resp.status_code == 200
            assert len(resp.data) == 3

    def test_strategy_status_view_fallback(self, tmp_path):
        from trading.services.strategy_orchestrator import StrategyOrchestrator

        StrategyOrchestrator.reset_instance()
        orig = StrategyOrchestrator._STATE_FILE
        StrategyOrchestrator._STATE_FILE = tmp_path / "orch_state.json"
        try:
            with patch(
                "core.platform_bridge.ensure_platform_imports", side_effect=ImportError("no module")
            ):
                resp = self.client.get("/api/signals/strategy-status/", {"asset_class": "crypto"})
                assert resp.status_code == 200
                for strat in resp.data:
                    assert strat["recommended_action"] == "active"
        finally:
            StrategyOrchestrator._STATE_FILE = orig
            StrategyOrchestrator.reset_instance()

    def test_ml_prediction_list_view(self):
        MLPrediction.objects.create(
            model_id="m1",
            symbol="BTC/USDT",
            probability=0.7,
            confidence=0.8,
            direction="up",
        )
        MLPrediction.objects.create(
            model_id="m1",
            symbol="BTC/USDT",
            probability=0.4,
            confidence=0.6,
            direction="down",
        )
        resp = self.client.get("/api/ml/predictions/BTC-USDT/")
        assert resp.status_code == 200
        assert len(resp.data) == 2

    def test_ml_prediction_list_view_limit(self):
        for _i in range(5):
            MLPrediction.objects.create(
                model_id="m1",
                symbol="ETH/USDT",
                probability=0.5,
                confidence=0.5,
                direction="up",
            )
        resp = self.client.get("/api/ml/predictions/ETH-USDT/", {"limit": 2})
        assert resp.status_code == 200
        assert len(resp.data) == 2

    def test_ml_model_performance_view(self):
        MLModelPerformance.objects.create(
            model_id="test_model",
            total_predictions=100,
            correct_predictions=65,
            rolling_accuracy=0.65,
        )
        resp = self.client.get("/api/ml/models/test_model/performance/")
        assert resp.status_code == 200
        assert resp.data["rolling_accuracy"] == 0.65

    def test_ml_model_performance_view_not_found(self):
        resp = self.client.get("/api/ml/models/nonexistent/performance/")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════
# Serializer tests
# ══════════════════════════════════════════════════════


class TestSignalSerializers:
    def test_signal_batch_request_serializer_valid(self):
        from analysis.serializers import SignalBatchRequestSerializer

        ser = SignalBatchRequestSerializer(
            data={
                "symbols": ["BTC/USDT", "ETH/USDT"],
                "asset_class": "crypto",
                "strategy_name": "CryptoInvestorV1",
            }
        )
        assert ser.is_valid()

    def test_signal_batch_request_serializer_empty_symbols(self):
        from analysis.serializers import SignalBatchRequestSerializer

        ser = SignalBatchRequestSerializer(data={"symbols": []})
        assert not ser.is_valid()

    def test_signal_batch_request_serializer_too_many(self):
        from analysis.serializers import SignalBatchRequestSerializer

        ser = SignalBatchRequestSerializer(data={"symbols": [f"S{i}" for i in range(51)]})
        assert not ser.is_valid()

    def test_entry_check_request_serializer(self):
        from analysis.serializers import EntryCheckRequestSerializer

        ser = EntryCheckRequestSerializer(
            data={"strategy": "CryptoInvestorV1", "asset_class": "crypto"}
        )
        assert ser.is_valid()

    def test_entry_check_request_serializer_invalid_asset(self):
        from analysis.serializers import EntryCheckRequestSerializer

        ser = EntryCheckRequestSerializer(data={"strategy": "CIV1", "asset_class": "bonds"})
        assert not ser.is_valid()

    @pytest.mark.django_db
    def test_ml_prediction_serializer(self):
        from analysis.serializers import MLPredictionSerializer

        pred = MLPrediction.objects.create(
            model_id="m1",
            symbol="BTC/USDT",
            probability=0.7,
            confidence=0.8,
            direction="up",
        )
        data = MLPredictionSerializer(pred).data
        assert data["symbol"] == "BTC/USDT"
        assert data["probability"] == 0.7
        assert data["prediction_id"]

    @pytest.mark.django_db
    def test_ml_model_performance_serializer(self):
        from analysis.serializers import MLModelPerformanceSerializer

        perf = MLModelPerformance.objects.create(
            model_id="m1",
            total_predictions=100,
            correct_predictions=65,
            rolling_accuracy=0.65,
        )
        data = MLModelPerformanceSerializer(perf).data
        assert data["model_id"] == "m1"
        assert data["rolling_accuracy"] == 0.65

    def test_composite_signal_response_serializer(self):
        from analysis.serializers import CompositeSignalResponseSerializer

        data = {
            "symbol": "BTC/USDT",
            "asset_class": "crypto",
            "timestamp": "2026-03-10T12:00:00+00:00",
            "composite_score": 72.5,
            "signal_label": "buy",
            "entry_approved": True,
            "position_modifier": 0.7,
            "hard_disabled": False,
            "components": {
                "technical": 80,
                "regime": 70,
                "ml": 65,
                "sentiment": 60,
                "scanner": 0,
                "win_rate": 50,
            },
            "confidences": {"ml": 0.8, "sentiment": 0.6, "regime": 0.9},
            "sources_available": ["regime", "ml"],
            "reasoning": ["Score: 72.5"],
        }
        ser = CompositeSignalResponseSerializer(data=data)
        assert ser.is_valid(), ser.errors


# ══════════════════════════════════════════════════════
# Task executor tests
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTaskExecutors:
    def _progress_cb(self, progress, message):
        """Dummy progress callback."""

    def test_ml_predict_executor_no_watchlist(self):
        from core.services.task_registry import _run_ml_predict

        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch("core.platform_bridge.get_platform_config", return_value={"data": {}}),
        ):
            result = _run_ml_predict({"asset_class": "crypto"}, self._progress_cb)
            assert result["status"] == "skipped"

    def test_ml_predict_executor_with_symbols(self):
        from core.services.task_registry import _run_ml_predict

        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch(
                "core.platform_bridge.get_platform_config",
                return_value={
                    "data": {"watchlist": ["BTC/USDT"]},
                },
            ),
            patch(
                "analysis.services.signal_service.SignalService._get_ml_prediction",
                return_value=(0.7, 0.8),
            ),
            patch(
                "analysis.services.signal_service.SignalService._get_regime_state",
                return_value=None,
            ),
        ):
            result = _run_ml_predict({"asset_class": "crypto"}, self._progress_cb)
            assert result["status"] == "completed"
            assert result["predicted"] == 1
            assert MLPrediction.objects.count() == 1

    def test_ml_predict_executor_no_model(self):
        from core.services.task_registry import _run_ml_predict

        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch(
                "core.platform_bridge.get_platform_config",
                return_value={
                    "data": {"watchlist": ["BTC/USDT"]},
                },
            ),
            patch(
                "analysis.services.signal_service.SignalService._get_ml_prediction",
                return_value=(None, None),
            ),
        ):
            result = _run_ml_predict({"asset_class": "crypto"}, self._progress_cb)
            assert result["status"] == "completed"
            assert result["predicted"] == 0

    def test_ml_feedback_executor_no_predictions(self):
        from core.services.task_registry import _run_ml_feedback

        result = _run_ml_feedback({}, self._progress_cb)
        assert result["status"] == "completed"
        assert result["outcomes_filled"] == 0
        assert result["models_updated"] == 0

    def test_ml_feedback_executor_with_predictions(self):
        from core.services.task_registry import _run_ml_feedback

        pred = MLPrediction.objects.create(
            model_id="m1",
            symbol="BTC/USDT",
            probability=0.7,
            confidence=0.8,
            direction="up",
        )

        import pandas as pd

        mock_df = pd.DataFrame({"close": [100.0, 105.0]})
        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch("common.data_pipeline.pipeline.load_ohlcv", return_value=mock_df),
        ):
            result = _run_ml_feedback({}, self._progress_cb)
            assert result["outcomes_filled"] == 1
            pred.refresh_from_db()
            assert pred.correct is True
            assert pred.actual_direction == "up"

    def test_ml_feedback_executor_down_actual(self):
        from core.services.task_registry import _run_ml_feedback

        pred = MLPrediction.objects.create(
            model_id="m1",
            symbol="BTC/USDT",
            probability=0.7,
            confidence=0.8,
            direction="up",
        )

        import pandas as pd

        mock_df = pd.DataFrame({"close": [105.0, 100.0]})
        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch("common.data_pipeline.pipeline.load_ohlcv", return_value=mock_df),
        ):
            _run_ml_feedback({}, self._progress_cb)
            pred.refresh_from_db()
            assert pred.correct is False
            assert pred.actual_direction == "down"

    def test_ml_feedback_updates_model_performance(self):
        from core.services.task_registry import _run_ml_feedback

        # Create predictions with known outcomes
        MLPrediction.objects.create(
            model_id="m1",
            symbol="BTC/USDT",
            probability=0.7,
            confidence=0.8,
            direction="up",
            correct=True,
            actual_direction="up",
        )
        MLPrediction.objects.create(
            model_id="m1",
            symbol="ETH/USDT",
            probability=0.6,
            confidence=0.7,
            direction="up",
            correct=False,
            actual_direction="down",
        )

        result = _run_ml_feedback({}, self._progress_cb)
        assert result["models_updated"] >= 1
        perf = MLModelPerformance.objects.get(model_id="m1")
        assert perf.total_predictions == 2
        assert perf.correct_predictions == 1
        assert perf.rolling_accuracy == 0.5

    def test_ml_retrain_executor_no_flagged(self):
        from core.services.task_registry import _run_ml_retrain

        result = _run_ml_retrain({}, self._progress_cb)
        assert result["status"] == "completed"
        assert result["retrained"] == 0

    def test_ml_retrain_executor_with_flagged(self):
        from core.services.task_registry import _run_ml_retrain

        MLModelPerformance.objects.create(
            model_id="BTC_1h_kraken_20260310",
            total_predictions=100,
            correct_predictions=45,
            rolling_accuracy=0.45,
            retrain_recommended=True,
        )

        with patch("analysis.services.ml.MLService.train", return_value={"status": "completed"}):
            result = _run_ml_retrain({}, self._progress_cb)
            assert result["retrained"] == 1
            # Check flag was cleared
            perf = MLModelPerformance.objects.get(model_id="BTC_1h_kraken_20260310")
            assert perf.retrain_recommended is False

    def test_conviction_audit_executor_no_watchlist(self):
        from core.services.task_registry import _run_conviction_audit

        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch("core.platform_bridge.get_platform_config", return_value={"data": {}}),
        ):
            result = _run_conviction_audit({"asset_class": "crypto"}, self._progress_cb)
            assert result["status"] == "skipped"

    def test_conviction_audit_executor_with_symbols(self):
        from core.services.task_registry import _run_conviction_audit

        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch(
                "core.platform_bridge.get_platform_config",
                return_value={
                    "data": {"watchlist": ["BTC/USDT"]},
                },
            ),
            patch(
                "analysis.services.signal_service.SignalService.get_signal",
                return_value={
                    "composite_score": 72.5,
                    "signal_label": "buy",
                    "entry_approved": True,
                    "sources_available": ["regime", "ml"],
                },
            ),
        ):
            result = _run_conviction_audit({"asset_class": "crypto"}, self._progress_cb)
            assert result["status"] == "completed"
            assert result["symbols_audited"] == 1
            assert result["average_score"] == 72.5

    def test_strategy_orchestration_executor(self):
        from core.services.task_registry import _run_strategy_orchestration

        mock_state = MagicMock()
        mock_state.regime.value = "STRONG_TREND_DOWN"

        mock_detector_cls = MagicMock()
        mock_detector_cls.return_value.detect.return_value = mock_state

        with (
            patch("core.platform_bridge.ensure_platform_imports"),
            patch.dict(
                "sys.modules",
                {
                    "common.regime.regime_detector": MagicMock(RegimeDetector=mock_detector_cls),
                    "common.signals.constants": MagicMock(
                        ALIGNMENT_TABLES={
                            "crypto": {
                                mock_state.regime: {
                                    "CryptoInvestorV1": 0,
                                    "BollingerMeanReversion": 40,
                                    "VolatilityBreakout": 15,
                                }
                            },
                            "equity": {
                                mock_state.regime: {"EquityMomentum": 5, "EquityMeanReversion": 35}
                            },
                            "forex": {mock_state.regime: {"ForexTrend": 10, "ForexRange": 25}},
                        }
                    ),
                },
            ),
            patch("core.services.notification.NotificationService.send_telegram_sync"),
        ):
            result = _run_strategy_orchestration({}, self._progress_cb)
            assert result["status"] == "completed"
            assert result["paused"] >= 1

    def test_strategy_orchestration_fallback_on_error(self):
        from core.services.task_registry import _run_strategy_orchestration

        with patch(
            "core.platform_bridge.ensure_platform_imports", side_effect=ImportError("no module")
        ):
            result = _run_strategy_orchestration(
                {"asset_classes": ["crypto"]},
                self._progress_cb,
            )
            assert result["status"] == "completed"
            for r in result["results"]:
                assert r["action"] == "active"

    def test_registry_has_new_executors(self):
        from core.services.task_registry import TASK_REGISTRY

        new_executors = [
            "ml_predict",
            "ml_feedback",
            "ml_retrain",
            "conviction_audit",
            "strategy_orchestration",
        ]
        for name in new_executors:
            assert name in TASK_REGISTRY, f"{name} not in TASK_REGISTRY"
            assert callable(TASK_REGISTRY[name])

    def test_registry_total_count(self):
        from core.services.task_registry import TASK_REGISTRY

        assert len(TASK_REGISTRY) == 24  # 15 base + 5 IEB + 2 feedback + 2 new


# ══════════════════════════════════════════════════════
# URL routing tests
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSignalURLRouting:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from django.contrib.auth.models import User

        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser2", password="testpass")
        self.client.force_authenticate(user=self.user)

    def test_signal_detail_url_resolves(self):
        from django.urls import resolve

        match = resolve("/api/signals/BTC-USDT/")
        assert match.url_name == "signal-detail"

    def test_signal_batch_url_resolves(self):
        from django.urls import resolve

        match = resolve("/api/signals/batch/")
        assert match.url_name == "signal-batch"

    def test_entry_check_url_resolves(self):
        from django.urls import resolve

        match = resolve("/api/signals/BTC-USDT/entry-check/")
        assert match.url_name == "signal-entry-check"

    def test_strategy_status_url_resolves(self):
        from django.urls import resolve

        match = resolve("/api/signals/strategy-status/")
        assert match.url_name == "signal-strategy-status"

    def test_ml_prediction_list_url_resolves(self):
        from django.urls import resolve

        match = resolve("/api/ml/predictions/BTC-USDT/")
        assert match.url_name == "ml-prediction-list"

    def test_ml_model_performance_url_resolves(self):
        from django.urls import resolve

        match = resolve("/api/ml/models/test_model/performance/")
        assert match.url_name == "ml-model-performance"
