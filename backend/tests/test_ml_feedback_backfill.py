"""Tests for ML feedback backfill from Freqtrade paper trades."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.django_db
class TestBackfillFromFreqtrade:
    def _create_prediction(self, symbol="BTC/USDT", direction="up"):
        from analysis.models import MLPrediction
        return MLPrediction.objects.create(
            model_id="test_model",
            symbol=symbol,
            asset_class="crypto",
            probability=0.7,
            confidence=0.8,
            direction=direction,
            regime="weak_trend_up",
        )

    @patch("analysis.services.signal_feedback.requests")
    def test_matches_closed_trade_to_prediction(self, mock_requests):
        pred = self._create_prediction(direction="up")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "trades": [{
                "pair": "BTC/USDT",
                "close_date": "2026-01-01",
                "profit_ratio": 0.05,
            }]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        with patch("django.conf.settings.FREQTRADE_INSTANCES", [{"url": "http://localhost:8080"}]):
            from analysis.services.signal_feedback import SignalFeedbackService
            result = SignalFeedbackService.backfill_from_freqtrade()

        assert result["matched"] == 1
        pred.refresh_from_db()
        assert pred.correct is True
        assert pred.actual_direction == "up"

    @patch("analysis.services.signal_feedback.requests")
    def test_incorrect_prediction_marked(self, mock_requests):
        pred = self._create_prediction(direction="up")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "trades": [{"pair": "BTC/USDT", "close_date": "2026-01-01", "profit_ratio": -0.03}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        with patch("django.conf.settings.FREQTRADE_INSTANCES", [{"url": "http://localhost:8080"}]):
            from analysis.services.signal_feedback import SignalFeedbackService
            SignalFeedbackService.backfill_from_freqtrade()

        pred.refresh_from_db()
        assert pred.correct is False

    @patch("analysis.services.signal_feedback.requests")
    def test_open_trades_skipped(self, mock_requests):
        self._create_prediction()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "trades": [{"pair": "BTC/USDT", "close_date": None, "profit_ratio": 0}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        with patch("django.conf.settings.FREQTRADE_INSTANCES", [{"url": "http://localhost:8080"}]):
            from analysis.services.signal_feedback import SignalFeedbackService
            result = SignalFeedbackService.backfill_from_freqtrade()

        assert result["matched"] == 0

    @patch("analysis.services.signal_feedback.requests")
    def test_no_matching_prediction(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "trades": [{"pair": "XRP/USDT", "close_date": "2026-01-01", "profit_ratio": 0.1}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        with patch("django.conf.settings.FREQTRADE_INSTANCES", [{"url": "http://localhost:8080"}]):
            from analysis.services.signal_feedback import SignalFeedbackService
            result = SignalFeedbackService.backfill_from_freqtrade()

        assert result["unmatched"] == 1

    @patch("analysis.services.signal_feedback.requests")
    def test_api_failure_graceful(self, mock_requests):
        mock_requests.get.side_effect = Exception("connection refused")

        with patch("django.conf.settings.FREQTRADE_INSTANCES", [{"url": "http://localhost:8080"}]):
            from analysis.services.signal_feedback import SignalFeedbackService
            result = SignalFeedbackService.backfill_from_freqtrade()

        assert result["errors"] == 1
        assert result["matched"] == 0

    def test_no_instances_returns_zero(self):
        with patch("django.conf.settings.FREQTRADE_INSTANCES", []):
            from analysis.services.signal_feedback import SignalFeedbackService
            result = SignalFeedbackService.backfill_from_freqtrade()

        assert result["matched"] == 0
        assert result["errors"] == 0

    @patch("analysis.services.signal_feedback.requests")
    def test_empty_url_skipped(self, mock_requests):
        with patch("django.conf.settings.FREQTRADE_INSTANCES", [{"url": ""}]):
            from analysis.services.signal_feedback import SignalFeedbackService
            SignalFeedbackService.backfill_from_freqtrade()

        mock_requests.get.assert_not_called()
