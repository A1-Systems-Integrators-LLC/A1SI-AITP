"""
Tests for IEB Phase 7 — Risk Manager Enhancement
==================================================
Covers:
- signal_modifier param in calculate_position_size (common/risk/risk_manager.py)
- Adaptive risk tightening in periodic_risk_check (backend/risk/services/risk.py)
- composite_score in TradeCheckView + TradeCheckLog (backend/risk/views.py)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

# Ensure project root is on sys.path for common.* imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.risk.risk_manager import RiskLimits, RiskManager


# ── signal_modifier Tests ──────────────────────────────────────────


class TestSignalModifier:
    """Tests for signal_modifier parameter in calculate_position_size."""

    def _make_rm(self, equity: float = 10000.0) -> RiskManager:
        rm = RiskManager(limits=RiskLimits(max_single_trade_risk=0.02))
        rm.state.total_equity = equity
        rm.state.peak_equity = equity
        return rm

    def test_signal_modifier_scales_size(self):
        rm = self._make_rm()
        base = rm.calculate_position_size(100.0, 95.0)
        modified = rm.calculate_position_size(100.0, 95.0, signal_modifier=0.5)
        assert modified == pytest.approx(base * 0.5, rel=1e-6)

    def test_signal_modifier_1_0_no_change(self):
        rm = self._make_rm()
        base = rm.calculate_position_size(100.0, 95.0)
        modified = rm.calculate_position_size(100.0, 95.0, signal_modifier=1.0)
        assert modified == pytest.approx(base, rel=1e-6)

    def test_signal_modifier_clamped_lower(self):
        """signal_modifier below 0.2 gets clamped to 0.2."""
        rm = self._make_rm()
        base = rm.calculate_position_size(100.0, 95.0)
        modified = rm.calculate_position_size(100.0, 95.0, signal_modifier=0.05)
        assert modified == pytest.approx(base * 0.2, rel=1e-6)

    def test_signal_modifier_clamped_upper(self):
        """signal_modifier above 1.5 gets clamped to 1.5."""
        rm = self._make_rm()
        base = rm.calculate_position_size(100.0, 95.0)
        modified = rm.calculate_position_size(100.0, 95.0, signal_modifier=2.0)
        assert modified == pytest.approx(base * 1.5, rel=1e-6)

    def test_signal_modifier_none_no_effect(self):
        rm = self._make_rm()
        base = rm.calculate_position_size(100.0, 95.0)
        modified = rm.calculate_position_size(100.0, 95.0, signal_modifier=None)
        assert modified == pytest.approx(base, rel=1e-6)

    def test_signal_modifier_stacks_with_regime(self):
        """Both modifiers applied: regime first, then signal."""
        rm = self._make_rm()
        base = rm.calculate_position_size(100.0, 95.0)
        both = rm.calculate_position_size(100.0, 95.0, regime_modifier=0.8, signal_modifier=0.5)
        assert both == pytest.approx(base * 0.8 * 0.5, rel=1e-6)

    def test_signal_modifier_1_5_increases_size(self):
        """High conviction (1.5) increases position size."""
        rm = self._make_rm()
        base = rm.calculate_position_size(100.0, 95.0)
        modified = rm.calculate_position_size(100.0, 95.0, signal_modifier=1.5)
        assert modified > base
        assert modified == pytest.approx(base * 1.5, rel=1e-6)

    def test_signal_modifier_with_zero_price_risk(self):
        """Stop loss = entry → 0 size regardless of modifier."""
        rm = self._make_rm()
        size = rm.calculate_position_size(100.0, 100.0, signal_modifier=1.5)
        assert size == 0.0


# ── Adaptive Risk Tightening Tests ──────────────────────────────────


class TestAdaptiveRiskTightening(TestCase):
    """Tests for regime-based adaptive risk tightening in periodic_risk_check."""

    def setUp(self):
        from risk.models import RiskLimits as RLModel
        from risk.models import RiskState

        self.state = RiskState.objects.create(
            portfolio_id=99,
            total_equity=10000,
            peak_equity=10000,
            daily_start_equity=10000,
        )
        self.limits = RLModel.objects.create(
            portfolio_id=99,
            max_portfolio_drawdown=0.15,
            max_daily_loss=0.05,
        )

    @patch("risk.services.risk.RiskManagementService._get_regime_risk_multiplier")
    @patch("risk.services.risk.RiskManagementService.record_metrics")
    def test_strong_trend_down_tightens_50pct(self, mock_metrics, mock_regime):
        """STRONG_TREND_DOWN tightens limits by 50%."""
        mock_regime.return_value = (0.5, "STRONG_TREND_DOWN")
        from risk.services.risk import RiskManagementService

        result = RiskManagementService.periodic_risk_check(99)
        assert result["status"] == "ok"
        assert result["regime_tightening"]["regime"] == "STRONG_TREND_DOWN"
        assert result["regime_tightening"]["multiplier"] == 0.5
        assert result["regime_tightening"]["effective_daily_loss"] == pytest.approx(0.025)
        assert result["regime_tightening"]["effective_drawdown"] == pytest.approx(0.075)

    @patch("risk.services.risk.RiskManagementService._get_regime_risk_multiplier")
    @patch("risk.services.risk.RiskManagementService.record_metrics")
    def test_high_volatility_tightens_30pct(self, mock_metrics, mock_regime):
        mock_regime.return_value = (0.7, "HIGH_VOLATILITY")
        from risk.services.risk import RiskManagementService

        result = RiskManagementService.periodic_risk_check(99)
        assert result["regime_tightening"]["multiplier"] == 0.7
        assert result["regime_tightening"]["effective_daily_loss"] == pytest.approx(0.035)

    @patch("risk.services.risk.RiskManagementService._get_regime_risk_multiplier")
    @patch("risk.services.risk.RiskManagementService.record_metrics")
    def test_normal_regime_no_tightening(self, mock_metrics, mock_regime):
        mock_regime.return_value = (1.0, "STRONG_TREND_UP")
        from risk.services.risk import RiskManagementService

        result = RiskManagementService.periodic_risk_check(99)
        assert "regime_tightening" not in result

    @patch("risk.services.risk.RiskManagementService._get_regime_risk_multiplier")
    @patch("risk.services.risk.RiskManagementService.record_metrics")
    @patch("risk.services.risk.RiskManagementService.send_notification")
    def test_tightened_drawdown_triggers_halt(self, mock_notify, mock_metrics, mock_regime):
        """When tightened drawdown limit is breached, auto-halt fires."""
        mock_regime.return_value = (0.5, "STRONG_TREND_DOWN")
        # Set drawdown at 8% — normally OK (limit 15%), but tightened to 7.5%
        self.state.total_equity = 9200
        self.state.peak_equity = 10000
        self.state.save()

        from risk.services.risk import RiskManagementService

        result = RiskManagementService.periodic_risk_check(99)
        assert result["status"] == "auto_halted"
        assert "STRONG_TREND_DOWN" in result["reason"]

    @patch("risk.services.risk.RiskManagementService._get_regime_risk_multiplier")
    @patch("risk.services.risk.RiskManagementService.record_metrics")
    @patch("risk.services.risk.RiskManagementService.send_notification")
    def test_tightened_daily_loss_triggers_halt(self, mock_notify, mock_metrics, mock_regime):
        """When tightened daily loss limit is breached, auto-halt fires."""
        mock_regime.return_value = (0.5, "STRONG_TREND_DOWN")
        # Daily loss at 3% — normally OK (limit 5%), but tightened to 2.5%
        self.state.daily_pnl = -300
        self.state.total_equity = 10000
        self.state.save()

        from risk.services.risk import RiskManagementService

        result = RiskManagementService.periodic_risk_check(99)
        assert result["status"] == "auto_halted"
        assert "STRONG_TREND_DOWN" in result["reason"]

    @patch("risk.services.risk.RiskManagementService._get_regime_risk_multiplier")
    @patch("risk.services.risk.RiskManagementService.record_metrics")
    @patch("risk.services.risk.RiskManagementService.send_notification")
    def test_tightened_warning_at_80pct(self, mock_notify, mock_metrics, mock_regime):
        """Warning fires at 80% of the tightened (effective) limit."""
        mock_regime.return_value = (0.5, "STRONG_TREND_DOWN")
        # Effective drawdown limit = 7.5%, 80% of that = 6%
        # Set drawdown to 6.5% (between 6% and 7.5%)
        self.state.total_equity = 9350
        self.state.peak_equity = 10000
        self.state.save()

        from risk.services.risk import RiskManagementService

        result = RiskManagementService.periodic_risk_check(99)
        assert result["status"] == "warning"
        assert "STRONG_TREND_DOWN" in result["warning"]

    def test_regime_multiplier_handles_detection_failure(self):
        """If regime detection fails, multiplier defaults to 1.0."""
        from risk.services.risk import RiskManagementService

        with patch("risk.services.risk.ensure_platform_imports", side_effect=ImportError("no module")):
            mult, name = RiskManagementService._get_regime_risk_multiplier()
            assert mult == 1.0
            assert name == "UNKNOWN"

    def test_weak_trend_down_tightens_15pct(self):
        """WEAK_TREND_DOWN applies 0.85 multiplier."""
        from risk.services.risk import RiskManagementService

        with patch("risk.services.risk.ensure_platform_imports"):
            mock_detector = MagicMock()
            mock_detector.detect.return_value = {"regime": "WEAK_TREND_DOWN"}
            with patch.dict("sys.modules", {"common.regime.regime_detector": MagicMock(RegimeDetector=lambda: mock_detector)}):
                mult, name = RiskManagementService._get_regime_risk_multiplier()
                assert mult == 0.85
                assert name == "WEAK_TREND_DOWN"


# ── composite_score Tests ──────────────────────────────────────────


class TestCompositeScoreTradeCheck(TestCase):
    """Tests for composite_score in TradeCheckView and TradeCheckLog."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        from risk.models import RiskLimits as RLModel
        from risk.models import RiskState

        User = get_user_model()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = APIClient()

        RiskState.objects.create(
            portfolio_id=1,
            total_equity=10000,
            peak_equity=10000,
            daily_start_equity=10000,
        )
        RLModel.objects.create(portfolio_id=1)

    def test_trade_check_without_composite_score(self):
        """Backward compat: composite_score not required."""
        resp = self.client.post(
            "/api/risk/1/check-trade/",
            {"symbol": "BTC/USDT", "side": "buy", "size": 0.1, "entry_price": 50000},
            format="json",
        )
        assert resp.status_code == 200
        assert "composite_score" not in resp.json()

    def test_trade_check_with_composite_score(self):
        """composite_score is accepted and returned when provided."""
        resp = self.client.post(
            "/api/risk/1/check-trade/",
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "size": 0.1,
                "entry_price": 50000,
                "composite_score": 82.5,
            },
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["composite_score"] == 82.5

    def test_composite_score_persisted_in_trade_log(self):
        """composite_score is stored in TradeCheckLog."""
        from risk.models import TradeCheckLog

        self.client.post(
            "/api/risk/1/check-trade/",
            {
                "symbol": "ETH/USDT",
                "side": "buy",
                "size": 0.5,
                "entry_price": 3000,
                "composite_score": 71.0,
            },
            format="json",
        )
        log = TradeCheckLog.objects.filter(symbol="ETH/USDT").first()
        assert log is not None
        assert log.composite_score == 71.0

    def test_composite_score_null_when_not_provided(self):
        """composite_score is null in log when not provided."""
        from risk.models import TradeCheckLog

        self.client.post(
            "/api/risk/1/check-trade/",
            {"symbol": "SOL/USDT", "side": "buy", "size": 1.0, "entry_price": 100},
            format="json",
        )
        log = TradeCheckLog.objects.filter(symbol="SOL/USDT").first()
        assert log is not None
        assert log.composite_score is None

    def test_composite_score_validation_min(self):
        """composite_score below 0 is rejected."""
        resp = self.client.post(
            "/api/risk/1/check-trade/",
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "size": 0.1,
                "entry_price": 50000,
                "composite_score": -5,
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_composite_score_validation_max(self):
        """composite_score above 100 is rejected."""
        resp = self.client.post(
            "/api/risk/1/check-trade/",
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "size": 0.1,
                "entry_price": 50000,
                "composite_score": 150,
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_composite_score_in_trade_log_serializer(self):
        """TradeCheckLogSerializer includes composite_score field."""
        from risk.models import TradeCheckLog
        from risk.serializers import TradeCheckLogSerializer

        log = TradeCheckLog.objects.create(
            portfolio_id=1,
            symbol="BTC/USDT",
            side="buy",
            size=0.1,
            entry_price=50000,
            approved=True,
            reason="approved",
            composite_score=85.0,
        )
        data = TradeCheckLogSerializer(log).data
        assert data["composite_score"] == 85.0
