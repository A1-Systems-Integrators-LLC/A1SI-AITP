"""Tests for recommended changes: per-asset-class risk limits, scanner/macro signal
weights, task retry mechanism, signal health endpoint, and risk threshold adjustments.
"""

import os
import sys
import time
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

from common.risk.risk_manager import RiskLimits, RiskManager


# ══════════════════════════════════════════════════════
# Per-asset-class risk limits
# ══════════════════════════════════════════════════════


class TestPerAssetClassRiskLimits:
    """Verify check_new_trade() uses per-asset-class overrides."""

    # Mock market hours as open for all equity/forex tests
    _market_open_patch = patch(
        "common.market_hours.sessions.MarketHoursService.is_market_open",
        return_value=True,
    )

    def setup_method(self):
        self._market_open_patch.start()

    def teardown_method(self):
        self._market_open_patch.stop()

    def _make_rm(self, **limit_kwargs) -> RiskManager:
        defaults = {
            "max_portfolio_drawdown": 0.40,
            "max_single_trade_risk": 0.08,
            "max_daily_loss": 0.15,
            "max_position_size_pct": 0.35,
        }
        defaults.update(limit_kwargs)
        rm = RiskManager(limits=RiskLimits(**defaults))
        rm.state.total_equity = 10000.0
        rm.state.peak_equity = 10000.0
        rm.state.daily_start_equity = 10000.0
        return rm

    def test_crypto_uses_global_limits(self):
        """Crypto has no overrides — should use global 35% position limit."""
        rm = self._make_rm()
        # 34% position should pass for crypto (under 35%)
        approved, _ = rm.check_new_trade(
            "BTC/USDT", "buy", 0.068, 50000.0, asset_class="crypto"
        )
        assert approved

    def test_equity_rejects_large_position(self):
        """Equity max_position_size_pct is 5% — a 10% position should be rejected."""
        rm = self._make_rm()
        # 10% of $10,000 = $1,000 position → exceeds equity 5% limit
        approved, reason = rm.check_new_trade(
            "AAPL", "buy", 5.0, 200.0, asset_class="equity"
        )
        assert not approved
        assert "Position too large" in reason
        assert "5.00%" in reason  # Should show equity-specific limit

    def test_equity_approves_small_position(self):
        """Equity 4% position should pass under 5% limit."""
        rm = self._make_rm()
        # 4% of $10,000 = $400 position
        approved, _ = rm.check_new_trade(
            "AAPL", "buy", 2.0, 200.0, asset_class="equity"
        )
        assert approved

    def test_equity_daily_loss_limit_3pct(self):
        """Equity daily loss limit is 3% — should reject when exceeded."""
        rm = self._make_rm()
        rm.state.total_equity = 9600.0  # -4% from start = below 3% limit
        approved, reason = rm.check_new_trade(
            "MSFT", "buy", 1.0, 100.0, asset_class="equity"
        )
        assert not approved
        assert "Daily loss limit" in reason

    def test_crypto_daily_loss_allows_up_to_15pct(self):
        """Crypto daily loss at 10% should still allow trades (limit is 15%)."""
        rm = self._make_rm()
        rm.state.total_equity = 9000.0  # -10% from start
        approved, _ = rm.check_new_trade(
            "BTC/USDT", "buy", 0.001, 50000.0, asset_class="crypto"
        )
        assert approved

    def test_forex_uses_global_position_limit(self):
        """Forex max_position_size_pct is 35% (same as global)."""
        rm = self._make_rm()
        # 30% of $10,000 = $3,000 position — should pass for forex
        approved, _ = rm.check_new_trade(
            "EUR/USD", "buy", 2500.0, 1.2, asset_class="forex"
        )
        assert approved

    def test_equity_trade_risk_uses_asset_override(self):
        """Equity max_single_trade_risk is 3% — wide stop should be rejected."""
        rm = self._make_rm()
        # Entry $200, stop $170 → 15% risk per unit, 2x equity limit (3%) = 6%
        # 15% > 6%, should reject
        approved, reason = rm.check_new_trade(
            "AAPL", "buy", 2.0, 200.0, stop_loss_price=170.0, asset_class="equity"
        )
        assert not approved
        assert "Stop loss too wide" in reason

    def test_overrides_dict_structure(self):
        """Verify _ASSET_CLASS_OVERRIDES has correct keys."""
        overrides = RiskManager._ASSET_CLASS_OVERRIDES
        assert "equity" in overrides
        assert "forex" in overrides
        assert "crypto" not in overrides  # Crypto uses global

        assert overrides["equity"]["max_position_size_pct"] == 0.05
        assert overrides["equity"]["max_daily_loss"] == 0.03
        assert overrides["forex"]["max_position_size_pct"] == 0.35


# ══════════════════════════════════════════════════════
# Signal weights (scanner + macro activated)
# ══════════════════════════════════════════════════════


class TestSignalWeights:
    """Verify scanner and macro weights are now active."""

    def test_weights_sum_to_one(self):
        from common.signals.constants import DEFAULT_WEIGHTS

        total = sum(DEFAULT_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_scanner_weight_active(self):
        from common.signals.constants import DEFAULT_WEIGHTS

        assert DEFAULT_WEIGHTS["scanner"] > 0
        assert DEFAULT_WEIGHTS["scanner"] == 0.05

    def test_macro_weight_active(self):
        from common.signals.constants import DEFAULT_WEIGHTS

        assert DEFAULT_WEIGHTS["macro"] > 0
        assert DEFAULT_WEIGHTS["macro"] == 0.05

    def test_technical_reduced_from_50(self):
        from common.signals.constants import DEFAULT_WEIGHTS

        assert DEFAULT_WEIGHTS["technical"] == 0.45

    def test_regime_reduced_from_30(self):
        from common.signals.constants import DEFAULT_WEIGHTS

        assert DEFAULT_WEIGHTS["regime"] == 0.25

    def test_unchanged_weights(self):
        from common.signals.constants import DEFAULT_WEIGHTS

        assert DEFAULT_WEIGHTS["ml"] == 0.00
        assert DEFAULT_WEIGHTS["sentiment"] == 0.05
        assert DEFAULT_WEIGHTS["win_rate"] == 0.10
        assert DEFAULT_WEIGHTS["funding"] == 0.05

    def test_scanner_score_flows_to_aggregator(self):
        """Scanner score should be weighted when provided to aggregator."""
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()
        result = agg.compute(
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy_name="CryptoInvestorV1",
            technical_score=70.0,
            scanner_score=90.0,
        )
        # Scanner should contribute to composite (weight 0.05)
        assert result.scanner_score > 0
        assert result.composite_score > 0

    def test_macro_score_flows_to_aggregator(self):
        """Macro score should be weighted when provided to aggregator."""
        from common.signals.aggregator import SignalAggregator

        agg = SignalAggregator()
        # With macro provided
        result_with = agg.compute(
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy_name="CryptoInvestorV1",
            technical_score=70.0,
            macro_score=80.0,
        )
        # Without macro
        result_without = agg.compute(
            symbol="BTC/USDT",
            asset_class="crypto",
            strategy_name="CryptoInvestorV1",
            technical_score=70.0,
        )
        # Scores should differ when macro is provided
        assert result_with.composite_score != result_without.composite_score


# ══════════════════════════════════════════════════════
# Task retry mechanism
# ══════════════════════════════════════════════════════


class TestTaskRetryMechanism:
    """Verify job runner retry constants and configuration."""

    def test_retry_constants_exist(self):
        from analysis.services.job_runner import MAX_RETRIES, NO_RETRY_TYPES, RETRY_BASE_DELAY_S

        assert MAX_RETRIES == 3
        assert RETRY_BASE_DELAY_S == 5

    def test_critical_tasks_not_retried(self):
        from analysis.services.job_runner import CRITICAL_TASK_TYPES, NO_RETRY_TYPES

        # All critical tasks should be in no-retry set
        for task_type in CRITICAL_TASK_TYPES:
            assert task_type in NO_RETRY_TYPES

    def test_no_retry_includes_frequent_tasks(self):
        from analysis.services.job_runner import NO_RETRY_TYPES

        assert "data_quality_check" in NO_RETRY_TYPES
        assert "autonomous_check" in NO_RETRY_TYPES

    def test_batch_tasks_are_retryable(self):
        """ML training, VBT screens, and backtests should be retried."""
        from analysis.services.job_runner import NO_RETRY_TYPES

        retryable = ["ml_training", "scheduled_vbt_screen", "scheduled_nautilus_backtest"]
        for task_type in retryable:
            assert task_type not in NO_RETRY_TYPES


class TestTaskRetryExecution:
    """Test retry loop logic at a unit level (avoids SQLite table lock in threads)."""

    def test_retry_loop_max_attempts_for_retryable(self):
        """Retryable tasks should get MAX_RETRIES + 1 attempts."""
        from analysis.services.job_runner import MAX_RETRIES, NO_RETRY_TYPES

        # A retryable job type gets MAX_RETRIES + 1 = 4 attempts
        max_attempts = 1 if "ml_training" in NO_RETRY_TYPES else MAX_RETRIES + 1
        assert max_attempts == 4

    def test_retry_loop_single_attempt_for_critical(self):
        """Critical/no-retry tasks should get exactly 1 attempt."""
        from analysis.services.job_runner import MAX_RETRIES, NO_RETRY_TYPES

        max_attempts = 1 if "risk_monitoring" in NO_RETRY_TYPES else MAX_RETRIES + 1
        assert max_attempts == 1

    def test_retry_backoff_schedule(self):
        """Verify exponential backoff delays: 5s, 10s, 20s."""
        from analysis.services.job_runner import RETRY_BASE_DELAY_S

        delays = [RETRY_BASE_DELAY_S * (2 ** i) for i in range(3)]
        assert delays == [5, 10, 20]

    def test_retry_logic_in_run_fn_wrapper(self):
        """Simulate retry loop logic: fail twice then succeed."""
        from analysis.services.job_runner import MAX_RETRIES, NO_RETRY_TYPES, RETRY_BASE_DELAY_S

        call_count = [0]

        def flaky_fn(params, progress_cb):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise RuntimeError("transient error")
            return {"status": "completed"}

        # Simulate the retry loop from _run_job
        max_attempts = MAX_RETRIES + 1  # Retryable task
        last_err = None
        result = None

        for attempt in range(max_attempts):
            try:
                result = flaky_fn({}, lambda p, m="": None)
                last_err = None
                break
            except Exception as e:
                last_err = e

        assert last_err is None
        assert result == {"status": "completed"}
        assert call_count[0] == 3  # Failed twice, succeeded on third


# ══════════════════════════════════════════════════════
# Signal health endpoint
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSignalHealthEndpoint:
    """Test /api/signals/health/ endpoint."""

    def _get_authed_client(self):
        from django.contrib.auth.models import User

        user, _ = User.objects.get_or_create(
            username="testuser",
            defaults={"is_active": True},
        )
        user.set_password("testpass123")
        user.save()
        client = APIClient()
        client.login(username="testuser", password="testpass123")
        return client

    def test_requires_auth(self):
        client = APIClient()
        resp = client.get("/api/signals/health/")
        assert resp.status_code in (401, 403)

    def test_returns_health_data(self):
        client = self._get_authed_client()
        resp = client.get("/api/signals/health/")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert "overall_status" in data
        assert "sources_ok" in data
        assert "sources_total" in data
        assert "asset_class" in data
        assert data["asset_class"] == "crypto"

    def test_asset_class_filter(self):
        client = self._get_authed_client()
        resp = client.get("/api/signals/health/?asset_class=equity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["asset_class"] == "equity"

    def test_all_sources_present(self):
        client = self._get_authed_client()
        resp = client.get("/api/signals/health/")
        data = resp.json()
        sources = data["sources"]
        expected = {"technical", "regime", "ml", "sentiment", "scanner", "win_rate", "funding", "macro"}
        assert set(sources.keys()) == expected

    def test_each_source_has_status(self):
        client = self._get_authed_client()
        resp = client.get("/api/signals/health/")
        data = resp.json()
        for name, source in data["sources"].items():
            assert "status" in source, f"Source {name} missing status"

    def test_funding_na_for_equity(self):
        client = self._get_authed_client()
        resp = client.get("/api/signals/health/?asset_class=equity")
        data = resp.json()
        assert data["sources"]["funding"]["status"] == "n/a"

    def test_overall_status_valid(self):
        client = self._get_authed_client()
        resp = client.get("/api/signals/health/")
        data = resp.json()
        assert data["overall_status"] in ("healthy", "degraded")


# ══════════════════════════════════════════════════════
# Risk threshold adjustments
# ══════════════════════════════════════════════════════


class TestRiskThresholdConfig:
    """Verify platform_config.yaml risk thresholds are tightened."""

    def test_platform_config_drawdown(self):
        import yaml

        config_path = PROJECT_ROOT / "configs" / "platform_config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert config["risk_management"]["max_portfolio_drawdown"] == 0.20

    def test_platform_config_daily_loss(self):
        import yaml

        config_path = PROJECT_ROOT / "configs" / "platform_config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert config["risk_management"]["max_daily_loss"] == 0.08

    def test_platform_config_trade_risk(self):
        import yaml

        config_path = PROJECT_ROOT / "configs" / "platform_config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert config["risk_management"]["max_single_trade_risk"] == 0.05

    def test_equity_overrides_unchanged(self):
        import yaml

        config_path = PROJECT_ROOT / "configs" / "platform_config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert config["equity"]["risk"]["max_position_size_pct"] == 0.05
        assert config["equity"]["risk"]["max_daily_loss"] == 0.03


# ══════════════════════════════════════════════════════
# Signal service pipeline health method
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSignalServicePipelineHealth:
    """Test SignalService.get_pipeline_health() directly."""

    def test_returns_dict(self):
        from analysis.services.signal_service import SignalService

        health = SignalService.get_pipeline_health("crypto")
        assert isinstance(health, dict)
        assert "sources" in health
        assert "timestamp" in health

    def test_crypto_includes_funding(self):
        from analysis.services.signal_service import SignalService

        health = SignalService.get_pipeline_health("crypto")
        assert "funding" in health["sources"]
        assert health["sources"]["funding"]["status"] != "n/a"

    def test_equity_funding_na(self):
        from analysis.services.signal_service import SignalService

        health = SignalService.get_pipeline_health("equity")
        assert health["sources"]["funding"]["status"] == "n/a"

    def test_source_latency_tracked(self):
        from analysis.services.signal_service import SignalService

        health = SignalService.get_pipeline_health("crypto")
        for name, source in health["sources"].items():
            if source.get("status") != "n/a":
                assert "latency_ms" in source, f"Source {name} missing latency_ms"
                assert source["latency_ms"] >= 0
