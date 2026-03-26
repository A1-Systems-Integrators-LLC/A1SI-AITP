"""Tests for financial accuracy: equity reconciliation, fee deduction, no phantom capital.

Ensures:
1. No phantom capital injected for forex symbols
2. Declared capital matches Freqtrade configs
3. P&L calculations deduct fees
4. RiskState defaults are zero (not $10,000)
5. CapitalLedger model exists and is writable
6. Equity sync computes correct values from actual data
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


# ══════════════════════════════════════════════════════
# RiskState defaults
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRiskStateDefaults:
    """RiskState must NOT default to $10,000."""

    def test_default_equity_is_zero(self):
        from risk.models import RiskState

        state = RiskState.objects.create(portfolio_id=9999)
        assert state.total_equity == 0.0
        assert state.peak_equity == 0.0
        assert state.daily_start_equity == 0.0
        state.delete()

    def test_default_pnl_fields_zero(self):
        from risk.models import RiskState

        state = RiskState.objects.create(portfolio_id=9998)
        assert state.crypto_pnl == 0.0
        assert state.forex_pnl == 0.0
        assert state.equity_pnl == 0.0
        assert state.declared_capital == 0.0
        state.delete()


# ══════════════════════════════════════════════════════
# CapitalLedger model
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCapitalLedger:
    """CapitalLedger provides immutable audit trail."""

    def test_create_ledger_entry(self):
        from risk.models import CapitalLedger

        entry = CapitalLedger.objects.create(
            portfolio_id=1,
            entry_type="equity_sync",
            source="test",
            amount=1300.0,
            balance_after=1300.0,
            details={"declared_capital": 1300.0, "crypto_pnl": 0.0},
        )
        assert entry.id is not None
        assert entry.entry_type == "equity_sync"
        assert entry.balance_after == 1300.0
        entry.delete()

    def test_ledger_ordering(self):
        from risk.models import CapitalLedger

        e1 = CapitalLedger.objects.create(
            portfolio_id=1, entry_type="equity_sync", source="test",
            amount=1300.0, balance_after=1300.0,
        )
        e2 = CapitalLedger.objects.create(
            portfolio_id=1, entry_type="equity_sync", source="test",
            amount=1290.0, balance_after=1290.0,
        )
        entries = list(CapitalLedger.objects.filter(portfolio_id=1))
        assert entries[0].id == e2.id  # Most recent first
        e1.delete()
        e2.delete()


# ══════════════════════════════════════════════════════
# Django settings wallet values
# ══════════════════════════════════════════════════════


class TestDjangoSettingsWallets:
    """Django settings must match actual Freqtrade configs."""

    def test_wallet_values_match_freqtrade_configs(self):
        from django.conf import settings

        instances = getattr(settings, "FREQTRADE_INSTANCES", None)
        if not instances:
            pytest.skip("FREQTRADE_INSTANCES not configured in test environment")
        wallets = {i["name"]: i["dry_run_wallet"] for i in instances}
        assert wallets["CryptoInvestorV1"] == 500.0
        assert wallets["BollingerMeanReversion"] == 500.0
        assert wallets["VolatilityBreakout"] == 300.0

    def test_total_declared_capital(self):
        from django.conf import settings

        instances = getattr(settings, "FREQTRADE_INSTANCES", None)
        if not instances:
            pytest.skip("FREQTRADE_INSTANCES not configured in test environment")
        total = sum(i["dry_run_wallet"] for i in instances)
        assert total == 1300.0


# ══════════════════════════════════════════════════════
# No phantom capital in equity sync
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestNoPhantomCapital:
    """Equity sync must not fabricate capital from forex symbol counts."""

    @patch("requests.get")
    def test_no_forex_initial_in_equity(self, mock_get):
        """Even with forex paper orders, no phantom $1,000/symbol added."""
        from core.services.task_registry import _sync_freqtrade_equity

        # Mock balance API response for one instance
        balance_resp = MagicMock()
        balance_resp.status_code = 200
        balance_resp.json.return_value = {
            "total_bot": 490.0,
            "total": 500.0,
            "starting_capital": 500.0,
        }
        balance_resp.raise_for_status = MagicMock()

        status_resp = MagicMock()
        status_resp.status_code = 200
        status_resp.json.return_value = []

        mock_get.side_effect = lambda url, **kw: (
            balance_resp if "balance" in url
            else status_resp if "status" in url
            else balance_resp
        )

        with patch("django.conf.settings.FREQTRADE_INSTANCES", [
            {"name": "Test", "url": "http://test:8080", "dry_run_wallet": 500.0, "enabled": True},
        ]):
            with patch("django.conf.settings.FREQTRADE_API_URL", ""):
                with patch("django.conf.settings.FREQTRADE_BMR_API_URL", ""):
                    with patch("django.conf.settings.FREQTRADE_VB_API_URL", ""):
                        result = _sync_freqtrade_equity()

        # Declared capital should be exactly the wallet amount
        assert result["declared_capital"] == 500.0
        # No phantom capital: equity = wallet + pnl, not wallet + phantom
        assert result["current_equity"] <= 510.0  # Can't exceed wallet + small pnl


# ══════════════════════════════════════════════════════
# Fee deduction in P&L
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFeeDeduction:
    """P&L calculations must deduct fees."""

    def test_performance_service_deducts_fees(self):
        from django.utils import timezone

        from trading.models import Order, OrderStatus, TradingMode

        now = timezone.now()
        # Create a buy and sell with fees
        buy = Order.objects.create(
            symbol="TEST/USD", side="buy", amount=100, price=1.0,
            filled=100, avg_fill_price=1.0, fee=0.50,
            status=OrderStatus.FILLED, portfolio_id=1,
            mode=TradingMode.PAPER, asset_class="forex", timestamp=now,
        )
        sell = Order.objects.create(
            symbol="TEST/USD", side="sell", amount=100, price=1.10,
            filled=100, avg_fill_price=1.10, fee=0.55,
            status=OrderStatus.FILLED, portfolio_id=1,
            mode=TradingMode.PAPER, asset_class="forex", timestamp=now,
        )

        from trading.services.performance import TradingPerformanceService

        metrics = TradingPerformanceService._compute_metrics([buy, sell])

        # Gross P&L = 100 * (1.10 - 1.00) = $10.00
        # Fees = $0.50 + $0.55 = $1.05
        # Net P&L = $10.00 - $1.05 = $8.95
        assert metrics["total_pnl"] == pytest.approx(8.95, abs=0.01)
        assert metrics["total_fees"] == pytest.approx(1.05, abs=0.01)

        buy.delete()
        sell.delete()

    def test_zero_fee_still_works(self):
        from django.utils import timezone

        from trading.models import Order, OrderStatus, TradingMode

        now = timezone.now()
        buy = Order.objects.create(
            symbol="TEST2/USD", side="buy", amount=10, price=50.0,
            filled=10, avg_fill_price=50.0, fee=0,
            status=OrderStatus.FILLED, portfolio_id=1,
            mode=TradingMode.PAPER, asset_class="crypto", timestamp=now,
        )
        sell = Order.objects.create(
            symbol="TEST2/USD", side="sell", amount=10, price=55.0,
            filled=10, avg_fill_price=55.0, fee=0,
            status=OrderStatus.FILLED, portfolio_id=1,
            mode=TradingMode.PAPER, asset_class="crypto", timestamp=now,
        )

        from trading.services.performance import TradingPerformanceService

        metrics = TradingPerformanceService._compute_metrics([buy, sell])
        assert metrics["total_pnl"] == pytest.approx(50.0, abs=0.01)
        assert metrics["total_fees"] == 0.0

        buy.delete()
        sell.delete()


# ══════════════════════════════════════════════════════
# Platform config consistency
# ══════════════════════════════════════════════════════


class TestPlatformConfigConsistency:
    """Freqtrade config files must match Django settings."""

    def test_freqtrade_config_wallets_match_settings(self):
        import json

        from django.conf import settings

        instances = getattr(settings, "FREQTRADE_INSTANCES", None)
        if not instances:
            pytest.skip("FREQTRADE_INSTANCES not configured in test environment")
        config_path = PROJECT_ROOT / "freqtrade" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                ft_config = json.load(f)
            ft_wallet = ft_config.get("dry_run_wallet", 0)
            django_wallet = next(
                (i["dry_run_wallet"] for i in instances
                 if i["name"] == "CryptoInvestorV1"), None,
            )
            assert ft_wallet == django_wallet, (
                f"Freqtrade config.json wallet ({ft_wallet}) != "
                f"Django settings ({django_wallet})"
            )
