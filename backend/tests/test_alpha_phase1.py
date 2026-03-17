"""Tests for Phase 1 — Alpha Maximization: Futures, Shorts, Thresholds, Profit Tracker."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ──────────────────────────────────────────────
# 1. Futures Config Validation
# ──────────────────────────────────────────────


class TestFuturesConfig:
    """Verify all 3 Freqtrade configs are set to futures mode."""

    CONFIG_DIR = Path(__file__).resolve().parents[2] / "freqtrade"

    @pytest.fixture(autouse=True)
    def _load_configs(self):
        self.configs = {}
        for name in ["config.json", "config_bmr.json", "config_vb.json"]:
            path = self.CONFIG_DIR / name
            if not path.exists():
                pytest.skip(f"{name} not found (gitignored)")
            with open(path) as f:
                self.configs[name] = json.load(f)

    @pytest.mark.parametrize("name", ["config.json", "config_bmr.json", "config_vb.json"])
    def test_trading_mode_futures(self, name):
        assert self.configs[name]["trading_mode"] == "futures"

    @pytest.mark.parametrize("name", ["config.json", "config_bmr.json", "config_vb.json"])
    def test_margin_mode_isolated(self, name):
        assert self.configs[name]["margin_mode"] == "isolated"

    @pytest.mark.parametrize("name", ["config.json", "config_bmr.json", "config_vb.json"])
    def test_max_open_trades_3(self, name):
        assert self.configs[name]["max_open_trades"] == 3

    @pytest.mark.parametrize("name", ["config.json", "config_bmr.json", "config_vb.json"])
    def test_stake_amount_80(self, name):
        assert self.configs[name]["stake_amount"] == 80

    @pytest.mark.parametrize("name", ["config.json", "config_bmr.json", "config_vb.json"])
    def test_dry_run_wallet_300(self, name):
        assert self.configs[name]["dry_run_wallet"] == 300

    @pytest.mark.parametrize("name", ["config.json", "config_bmr.json", "config_vb.json"])
    def test_ccxt_default_type_swap(self, name):
        ccxt_config = self.configs[name]["exchange"]["ccxt_config"]
        assert ccxt_config.get("defaultType") == "swap"


# ──────────────────────────────────────────────
# 2. Short Selling Enabled
# ──────────────────────────────────────────────


class TestShortSellingEnabled:
    """Verify can_short=True and short entry/exit logic in strategies."""

    def test_civ1_can_short(self):
        """CryptoInvestorV1 has can_short = True."""
        strategy_path = (
            Path(__file__).resolve().parents[2]
            / "freqtrade/user_data/strategies/CryptoInvestorV1.py"
        )
        content = strategy_path.read_text()
        assert "can_short = True" in content

    def test_bmr_can_short(self):
        strategy_path = (
            Path(__file__).resolve().parents[2]
            / "freqtrade/user_data/strategies/BollingerMeanReversion.py"
        )
        content = strategy_path.read_text()
        assert "can_short = True" in content

    def test_vb_can_short(self):
        strategy_path = (
            Path(__file__).resolve().parents[2]
            / "freqtrade/user_data/strategies/VolatilityBreakout.py"
        )
        content = strategy_path.read_text()
        assert "can_short = True" in content

    def test_civ1_has_enter_short(self):
        strategy_path = (
            Path(__file__).resolve().parents[2]
            / "freqtrade/user_data/strategies/CryptoInvestorV1.py"
        )
        content = strategy_path.read_text()
        assert '"enter_short"' in content
        assert '"exit_short"' in content

    def test_bmr_has_enter_short(self):
        strategy_path = (
            Path(__file__).resolve().parents[2]
            / "freqtrade/user_data/strategies/BollingerMeanReversion.py"
        )
        content = strategy_path.read_text()
        assert '"enter_short"' in content
        assert '"exit_short"' in content

    def test_vb_has_enter_short(self):
        strategy_path = (
            Path(__file__).resolve().parents[2]
            / "freqtrade/user_data/strategies/VolatilityBreakout.py"
        )
        content = strategy_path.read_text()
        assert '"enter_short"' in content
        assert '"exit_short"' in content

    def test_all_strategies_have_leverage_method(self):
        for name in ["CryptoInvestorV1.py", "BollingerMeanReversion.py", "VolatilityBreakout.py"]:
            path = (
                Path(__file__).resolve().parents[2]
                / f"freqtrade/user_data/strategies/{name}"
            )
            content = path.read_text()
            assert "def leverage(" in content, f"{name} missing leverage() method"


# ──────────────────────────────────────────────
# 3. Conviction Threshold Changes
# ──────────────────────────────────────────────


class TestConvictionThresholds:
    """Verify lowered conviction thresholds."""

    def test_crypto_threshold_40(self):
        from common.signals.asset_tuning import ASSET_CONFIGS

        assert ASSET_CONFIGS["crypto"].conviction_threshold == 40

    def test_equity_threshold_50(self):
        from common.signals.asset_tuning import ASSET_CONFIGS

        assert ASSET_CONFIGS["equity"].conviction_threshold == 50

    def test_forex_threshold_45(self):
        from common.signals.asset_tuning import ASSET_CONFIGS

        assert ASSET_CONFIGS["forex"].conviction_threshold == 45

    def test_hard_disable_empty(self):
        from common.signals.constants import HARD_DISABLE

        assert len(HARD_DISABLE) == 0

    def test_std_alignment_nonzero_crypto(self):
        from common.regime.regime_detector import Regime
        from common.signals.constants import CRYPTO_ALIGNMENT

        std = CRYPTO_ALIGNMENT[Regime.STRONG_TREND_DOWN]
        assert std["CryptoInvestorV1"] > 0
        assert std["VolatilityBreakout"] > 0

    def test_std_alignment_nonzero_equity(self):
        from common.regime.regime_detector import Regime
        from common.signals.constants import EQUITY_ALIGNMENT

        assert EQUITY_ALIGNMENT[Regime.STRONG_TREND_DOWN]["EquityMomentum"] > 0


class TestOrchestratorThresholds:
    """Verify lowered orchestrator thresholds."""

    def test_pause_threshold_5(self):
        from trading.services.strategy_orchestrator import StrategyOrchestrator

        assert StrategyOrchestrator.PAUSE_THRESHOLD == 5

    def test_reduce_threshold_20(self):
        from trading.services.strategy_orchestrator import StrategyOrchestrator

        assert StrategyOrchestrator.REDUCE_THRESHOLD == 20


# ──────────────────────────────────────────────
# 4. Risk Limit Changes
# ──────────────────────────────────────────────


class TestRiskLimitConfig:
    """Verify widened risk limits in platform_config.yaml."""

    @pytest.fixture(autouse=True)
    def _load_config(self):
        import yaml

        config_path = Path(__file__).resolve().parents[2] / "configs/platform_config.yaml"
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

    def test_max_portfolio_drawdown_40(self):
        assert self.config["risk_management"]["max_portfolio_drawdown"] == 0.40

    def test_max_daily_loss_15(self):
        assert self.config["risk_management"]["max_daily_loss"] == 0.15

    def test_max_single_trade_risk_8(self):
        assert self.config["risk_management"]["max_single_trade_risk"] == 0.08

    def test_max_leverage_5(self):
        assert self.config["risk_management"]["max_leverage"] == 5.0

    def test_max_position_size_35(self):
        assert self.config["risk_management"]["max_position_size_pct"] == 0.35

    def test_min_risk_reward_1(self):
        assert self.config["risk_management"]["min_risk_reward"] == 1.0

    def test_futures_trading_mode(self):
        assert self.config["freqtrade"]["trading_mode"] == "futures"


# ──────────────────────────────────────────────
# 5. Profit Reinvestment Tracker
# ──────────────────────────────────────────────


class TestProfitTracker:
    """Test ProfitTracker logic."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        from common.risk.profit_tracker import ProfitTracker

        ProfitTracker.reset_instance()
        self.state_path = tmp_path / "profit_tracker.json"
        self.tracker = ProfitTracker(state_path=self.state_path)

    def test_initial_state(self):
        state = self.tracker.get_state()
        assert state.base_capital == 500.0
        assert state.total_realized_pnl == 0.0
        assert state.reinvested_pool == 0.0
        assert state.reserved_pool == 0.0
        assert state.current_budget == 500.0
        assert state.total_equity == 500.0

    def test_stake_multiplier_at_baseline(self):
        assert self.tracker.get_stake_multiplier() == 1.0

    def test_record_winning_trade(self):
        self.tracker.record_trade(100.0)
        state = self.tracker.get_state()
        assert state.total_realized_pnl == 100.0
        assert state.reinvested_pool == 80.0  # 80% reinvested
        assert state.reserved_pool == 20.0  # 20% reserved
        assert state.winning_trades == 1
        assert state.total_trades == 1
        assert state.current_budget == 580.0
        assert state.total_equity == 600.0

    def test_stake_multiplier_after_profit(self):
        self.tracker.record_trade(250.0)  # $250 profit
        # reinvested = 200, budget = 700, multiplier = 700/500 = 1.4
        assert self.tracker.get_stake_multiplier() == pytest.approx(1.4)

    def test_record_losing_trade(self):
        self.tracker.record_trade(-50.0)
        state = self.tracker.get_state()
        assert state.total_realized_pnl == -50.0
        assert state.reinvested_pool == 0.0  # Can't go below 0
        assert state.losing_trades == 1
        assert state.largest_loss == -50.0

    def test_loss_reduces_reinvested_first(self):
        self.tracker.record_trade(100.0)  # +80 reinvested
        self.tracker.record_trade(-30.0)  # -30 from reinvested
        state = self.tracker.get_state()
        assert state.reinvested_pool == 50.0  # 80 - 30
        assert state.reserved_pool == 20.0  # Untouched
        assert state.current_budget == 550.0

    def test_loss_never_below_base(self):
        self.tracker.record_trade(-200.0)  # Huge loss
        assert self.tracker.get_stake_multiplier() == 1.0  # Never below 1.0
        assert self.tracker.get_state().current_budget == 500.0

    def test_persistence(self):
        from common.risk.profit_tracker import ProfitTracker

        self.tracker.record_trade(100.0)
        # Create new instance from same file
        tracker2 = ProfitTracker(state_path=self.state_path)
        state = tracker2.get_state()
        assert state.reinvested_pool == 80.0
        assert state.reserved_pool == 20.0

    def test_get_summary(self):
        self.tracker.record_trade(100.0)
        summary = self.tracker.get_summary()
        assert summary["base_capital"] == 500.0
        assert summary["current_budget"] == 580.0
        assert summary["total_equity"] == 600.0
        assert summary["stake_multiplier"] == pytest.approx(1.16)
        assert summary["win_rate"] == 1.0

    def test_win_rate(self):
        self.tracker.record_trade(50.0)
        self.tracker.record_trade(-10.0)
        self.tracker.record_trade(30.0)
        assert self.tracker.get_state().win_rate == pytest.approx(2 / 3)

    def test_largest_win_loss_tracking(self):
        self.tracker.record_trade(50.0)
        self.tracker.record_trade(100.0)
        self.tracker.record_trade(-30.0)
        self.tracker.record_trade(-60.0)
        state = self.tracker.get_state()
        assert state.largest_win == 100.0
        assert state.largest_loss == -60.0

    def test_corrupt_file_handled(self):
        from common.risk.profit_tracker import ProfitTracker

        self.state_path.write_text("not json{{{")
        tracker = ProfitTracker(state_path=self.state_path)
        assert tracker.get_state().base_capital == 500.0  # Falls back to defaults


# ──────────────────────────────────────────────
# 6. Profit Tracking API
# ──────────────────────────────────────────────


@pytest.mark.django_db
class TestProfitTrackingAPI:
    """Test the profit tracking API endpoint."""

    def test_profit_tracking_endpoint(self, client):
        from django.contrib.auth.models import User

        User.objects.create_user(username="testuser", password="testpass")
        client.login(username="testuser", password="testpass")
        resp = client.get("/api/risk/1/profit-tracking/")
        assert resp.status_code == 200
        data = resp.json()
        assert "base_capital" in data
        assert "stake_multiplier" in data
        assert "current_budget" in data


# ──────────────────────────────────────────────
# 7. Conviction Helpers - Side Parameter
# ──────────────────────────────────────────────


class TestConvictionHelpersSide:
    """Test that fetch_signal passes side parameter."""

    def test_fetch_signal_includes_side(self):
        """fetch_signal passes side to API."""
        import importlib
        import sys

        # Ensure the strategies dir is on path
        strategies_dir = str(
            Path(__file__).resolve().parents[2] / "freqtrade/user_data/strategies"
        )
        if strategies_dir not in sys.path:
            sys.path.insert(0, strategies_dir)

        import _conviction_helpers

        importlib.reload(_conviction_helpers)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"approved": True, "score": 75}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = _conviction_helpers.fetch_signal(
                "http://localhost:8000", "BTC/USDT", "CryptoInvestorV1", side="short",
            )

            call_args = mock_post.call_args
            assert call_args[1]["json"]["side"] == "short"
            assert result is not None
