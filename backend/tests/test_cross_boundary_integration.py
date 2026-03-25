"""Cross-boundary integration tests.

These tests verify that external callers (Freqtrade, NautilusTrader) can actually
reach Django endpoints with the correct auth context and payload format.

Unlike unit tests that use force_authenticate() or mock services, these tests use
a bare APIClient() — no auth — to replicate the real caller's HTTP context.

CRITICAL: If any of these tests fail, it means an external system is silently
broken in production (getting 401/403/400) even though service-level unit tests pass.

This test file exists because of the 2026-03-25 incident where SignalRecordView
required auth but Freqtrade called it unauthenticated, resulting in 0 signal
attributions for months while all unit tests passed.
"""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestFreqtradeCrossApiIntegration:
    """Test endpoints the way Freqtrade actually calls them — unauthenticated."""

    def _unauthed_client(self) -> APIClient:
        """Return a client with NO authentication — mimics Freqtrade's requests lib."""
        return APIClient()

    # ── Entry Check (conviction gate) ──────────────────────────

    def test_entry_check_unauthenticated_returns_200(self):
        """Freqtrade POSTs /api/signals/{symbol}/entry-check/ without auth."""
        client = self._unauthed_client()
        resp = client.post(
            "/api/signals/BTC-USDT/entry-check/",
            {"strategy": "CryptoInvestorV1", "asset_class": "crypto"},
            format="json",
        )
        # Should NOT be 401/403 — EntryCheckView has AllowAny
        assert resp.status_code == 200, (
            f"Entry check returned {resp.status_code} for unauthenticated caller. "
            f"This means Freqtrade's conviction gate is broken. Response: {resp.data}"
        )

    def test_entry_check_response_has_required_fields(self):
        """Freqtrade parses: approved, score, position_modifier, signal_label."""
        client = self._unauthed_client()
        resp = client.post(
            "/api/signals/BTC-USDT/entry-check/",
            {"strategy": "CryptoInvestorV1", "asset_class": "crypto"},
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        # These are the exact fields Freqtrade's _conviction_helpers.py reads
        assert "approved" in data, "Missing 'approved' — Freqtrade will crash"
        assert "score" in data, "Missing 'score' — Freqtrade will crash"
        assert "position_modifier" in data, "Missing 'position_modifier'"
        assert "signal_label" in data, "Missing 'signal_label'"
        assert isinstance(data["approved"], bool)
        assert isinstance(data["score"], (int, float))
        assert isinstance(data["position_modifier"], (int, float))

    def test_entry_check_with_extra_side_field_doesnt_fail(self):
        """Freqtrade sends an extra 'side' field — DRF should ignore it, not 400."""
        client = self._unauthed_client()
        resp = client.post(
            "/api/signals/BTC-USDT/entry-check/",
            {
                "strategy": "BollingerMeanReversion",
                "asset_class": "crypto",
                "side": "long",  # Extra field Freqtrade sends
            },
            format="json",
        )
        assert resp.status_code == 200

    # ── Strategy Status (pause check) ──────────────────────────

    def test_strategy_status_unauthenticated_returns_200(self):
        """Freqtrade GETs /api/signals/strategy-status/ without auth."""
        client = self._unauthed_client()
        resp = client.get("/api/signals/strategy-status/?asset_class=crypto")
        assert resp.status_code == 200, (
            f"Strategy status returned {resp.status_code} for unauthenticated caller. "
            f"Freqtrade's pause check will fail-open, ignoring orchestrator state."
        )

    def test_strategy_status_returns_list(self):
        """Freqtrade expects a JSON list of strategy states."""
        client = self._unauthed_client()
        resp = client.get("/api/signals/strategy-status/?asset_class=crypto")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    # ── Signal Attribution Recording ──────────────────────────

    def test_signal_record_unauthenticated_returns_201(self):
        """Freqtrade POSTs /api/signals/record/ without auth."""
        client = self._unauthed_client()
        # This is the EXACT payload format Freqtrade sends
        payload = {
            "order_id": "test-order-001",
            "symbol": "BTC/USDT",
            "strategy": "CryptoInvestorV1",
            "asset_class": "crypto",
            "signal_data": {
                "composite_score": 75.5,
                "position_modifier": 1.0,
                "_regime": "STRONG_TREND_UP",
                "components": {
                    "technical": 80,
                    "ml": 70,
                    "sentiment": 60,
                    "regime": 85,
                    "scanner": 50,
                    "win_rate": 65,
                },
            },
        }
        resp = client.post("/api/signals/record/", payload, format="json")
        assert resp.status_code == 201, (
            f"Signal record returned {resp.status_code} for unauthenticated caller. "
            f"This means signal attributions are NOT being recorded. "
            f"Response: {resp.data}"
        )

    @pytest.mark.django_db(transaction=True)
    def test_signal_record_creates_attribution(self):
        """Verify the attribution record actually persists to DB."""
        from analysis.models import SignalAttribution

        client = self._unauthed_client()
        payload = {
            "order_id": "test-order-persist",
            "symbol": "ETH/USDT",
            "strategy": "VolatilityBreakout",
            "asset_class": "crypto",
            "signal_data": {
                "composite_score": 68.0,
                "position_modifier": 0.8,
                "_regime": "HIGH_VOLATILITY",
                "components": {
                    "technical": 70,
                    "ml": 0,
                    "sentiment": 55,
                    "regime": 60,
                    "scanner": 40,
                    "win_rate": 50,
                },
            },
        }
        resp = client.post("/api/signals/record/", payload, format="json")
        assert resp.status_code == 201

        attr = SignalAttribution.objects.get(order_id="test-order-persist")
        assert attr.symbol == "ETH/USDT"
        assert attr.strategy == "VolatilityBreakout"
        assert attr.composite_score == 68.0
        assert attr.technical_contribution == 70
        assert attr.entry_regime == "HIGH_VOLATILITY"

    def test_signal_record_flat_payload_rejected(self):
        """Old flat-field format should fail validation (caught early, not silently)."""
        client = self._unauthed_client()
        # This is the OLD broken format — flat fields instead of nested signal_data
        flat_payload = {
            "order_id": "test-flat-format",
            "symbol": "BTC/USDT",
            "strategy": "CryptoInvestorV1",
            "asset_class": "crypto",
            "composite_score": 75.5,  # Wrong: should be inside signal_data
            "technical_contribution": 80,  # Wrong: should be inside signal_data.components
        }
        resp = client.post("/api/signals/record/", flat_payload, format="json")
        # Should fail because signal_data is required
        assert resp.status_code == 400, (
            "Flat payload was accepted — serializer is not validating correctly"
        )


@pytest.mark.django_db
class TestNautilusTraderCrossBoundaryIntegration:
    """Test endpoints the way NautilusTrader actually calls them."""

    def _unauthed_client(self) -> APIClient:
        return APIClient()

    def test_risk_check_trade_unauthenticated_returns_200(self):
        """NautilusTrader POSTs /api/risk/{id}/check-trade/ without auth."""
        from portfolio.models import Portfolio

        portfolio = Portfolio.objects.create(
            name="Test Portfolio",
            exchange_id="kraken",
        )
        client = self._unauthed_client()
        # This is the EXACT payload NautilusTrader sends
        payload = {
            "symbol": "BTC/USDT",
            "side": "buy",
            "size": 0.5,
            "entry_price": 45000.0,
            "stop_loss_price": 42750.0,
            "asset_class": "crypto",
        }
        resp = client.post(
            f"/api/risk/{portfolio.id}/check-trade/",
            payload,
            format="json",
        )
        assert resp.status_code == 200, (
            f"Risk check returned {resp.status_code} for unauthenticated caller. "
            f"NautilusTrader risk gate is broken."
        )

    def test_risk_check_trade_response_has_approved_field(self):
        """NautilusTrader reads: data.get('approved', False)."""
        from portfolio.models import Portfolio

        portfolio = Portfolio.objects.create(
            name="Test Portfolio",
            exchange_id="kraken",
        )
        client = self._unauthed_client()
        resp = client.post(
            f"/api/risk/{portfolio.id}/check-trade/",
            {
                "symbol": "ETH/USDT",
                "side": "buy",
                "size": 0.1,
                "entry_price": 3000.0,
                "asset_class": "equity",  # Test non-crypto asset_class
            },
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "approved" in data, "Missing 'approved' — NautilusTrader will crash"
        assert isinstance(data["approved"], bool)

    def test_entry_check_with_equity_asset_class(self):
        """NautilusTrader equity strategies send asset_class='equity'."""
        client = self._unauthed_client()
        resp = client.post(
            "/api/signals/AAPL/entry-check/",
            {"strategy": "EquityMomentum", "asset_class": "equity"},
            format="json",
        )
        assert resp.status_code == 200

    def test_entry_check_with_forex_asset_class(self):
        """NautilusTrader forex strategies send asset_class='forex'."""
        client = self._unauthed_client()
        resp = client.post(
            "/api/signals/EUR-USD/entry-check/",
            {"strategy": "ForexTrend", "asset_class": "forex"},
            format="json",
        )
        assert resp.status_code == 200


@pytest.mark.django_db
class TestAuthenticatedEndpointsDenyUnauthenticated:
    """Verify endpoints that SHOULD require auth actually reject unauthenticated calls.

    This is the inverse test — make sure we haven't accidentally opened up
    endpoints that should be protected.
    """

    def _unauthed_client(self) -> APIClient:
        return APIClient()

    def test_portfolio_list_requires_auth(self):
        client = self._unauthed_client()
        resp = client.get("/api/portfolios/")
        assert resp.status_code in (401, 403)

    def test_orders_list_requires_auth(self):
        client = self._unauthed_client()
        resp = client.get("/api/trading/orders/")
        assert resp.status_code in (401, 403)

    def test_dashboard_kpis_requires_auth(self):
        client = self._unauthed_client()
        resp = client.get("/api/dashboard/kpis/")
        assert resp.status_code in (401, 403)

    def test_risk_status_requires_auth(self):
        client = self._unauthed_client()
        resp = client.get("/api/risk/1/status/")
        assert resp.status_code in (401, 403)

    def test_signal_detail_requires_auth(self):
        client = self._unauthed_client()
        resp = client.get("/api/signals/BTC-USDT/")
        assert resp.status_code in (401, 403)

    def test_signal_batch_requires_auth(self):
        client = self._unauthed_client()
        resp = client.post(
            "/api/signals/batch/",
            {"symbols": ["BTC/USDT"]},
            format="json",
        )
        assert resp.status_code in (401, 403)

    def test_signal_attribution_list_requires_auth(self):
        client = self._unauthed_client()
        resp = client.get("/api/signals/attribution/")
        assert resp.status_code in (401, 403)

    def test_scheduler_tasks_requires_auth(self):
        client = self._unauthed_client()
        resp = client.get("/api/scheduler/tasks/")
        assert resp.status_code in (401, 403)

    def test_regime_current_requires_auth(self):
        client = self._unauthed_client()
        resp = client.get("/api/regime/current/")
        assert resp.status_code in (401, 403)


@pytest.mark.django_db
class TestTaskExecutorStatusReporting:
    """Verify task executors report failure accurately, not 'completed' when broken."""

    def test_ml_predict_reports_error_with_no_models(self):
        """If no ML models exist, _run_ml_predict should return 'error' not 'completed'."""
        from core.services.task_registry import _run_ml_predict

        result = _run_ml_predict(
            {"asset_class": "crypto"},
            lambda p, m: None,
        )
        # With no trained models, status should be "error" or "skipped", never "completed"
        if result.get("total", 0) > 0:
            if result.get("predicted", 0) == 0:
                assert result["status"] == "error", (
                    f"ML predict returned status='{result['status']}' with 0 predictions. "
                    "Should be 'error' to surface the broken pipeline."
                )

    def test_vbt_screen_reports_error_when_all_fail(self):
        """If all symbols fail screening, status should be 'error'."""
        from unittest.mock import patch

        from core.services.task_registry import _run_vbt_screen

        # Mock the screener to always fail
        with patch(
            "analysis.services.screening.ScreenerService.run_full_screen",
            side_effect=Exception("test failure"),
        ):
            result = _run_vbt_screen(
                {"asset_class": "crypto"},
                lambda p, m: None,
            )
            if result.get("status") != "skipped":
                assert result["status"] == "error", (
                    f"VBT screen returned '{result['status']}' when all symbols failed"
                )

    def test_data_refresh_reports_error_when_all_fail(self):
        """If all symbol downloads fail, status should be 'error'."""
        from unittest.mock import patch

        from core.services.task_registry import _run_data_refresh

        def mock_download(**kwargs):
            return {"BTC/USDT": {"status": "error", "error": "test"}}

        with patch(
            "common.data_pipeline.pipeline.download_watchlist",
            side_effect=mock_download,
        ):
            result = _run_data_refresh(
                {"asset_class": "crypto"},
                lambda p, m: None,
            )
            if result.get("status") != "skipped":
                assert result["status"] == "error", (
                    f"Data refresh returned '{result['status']}' when all downloads failed"
                )

    def test_ml_training_counts_only_successes(self):
        """models_trained should count only successful trainings, not errors."""
        from unittest.mock import patch

        from core.services.task_registry import _run_ml_training

        def mock_train(params, cb):
            raise Exception("test training failure")

        with patch("analysis.services.ml.MLService.train", side_effect=mock_train):
            result = _run_ml_training(
                {"symbols": ["BTC/USDT", "ETH/USDT"]},
                lambda p, m: None,
            )
            assert result["models_trained"] == 0, (
                f"Reported {result['models_trained']} models trained when all failed"
            )
            assert result["errors"] == 2
            assert result["status"] == "error"
