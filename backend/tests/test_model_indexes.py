"""Tests for P5-2: Model Indexes Migration."""

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent

from analysis.models import BackgroundJob, BacktestResult, ScreenResult, WorkflowRun
from risk.models import AlertLog, RiskLimitChange, TradeCheckLog
from trading.models import Order


def _index_names(model_cls) -> set[str]:
    return {idx.name for idx in model_cls._meta.indexes}


class TestBacktestResultIndexes:
    def test_asset_strategy_index(self):
        assert "idx_backtest_asset_strategy" in _index_names(BacktestResult)

    def test_framework_asset_index(self):
        assert "idx_backtest_framework_asset" in _index_names(BacktestResult)

    def test_symbol_timeframe_index(self):
        assert "idx_backtest_symbol_tf" in _index_names(BacktestResult)


class TestBackgroundJobIndexes:
    def test_status_created_index(self):
        assert "idx_job_status_created" in _index_names(BackgroundJob)


class TestScreenResultIndexes:
    def test_asset_created_index(self):
        assert "idx_screen_asset_created" in _index_names(ScreenResult)


class TestWorkflowRunIndexes:
    def test_workflow_created_index(self):
        assert "idx_wfrun_workflow_created" in _index_names(WorkflowRun)


class TestOrderIndexes:
    def test_portfolio_status_timestamp_index(self):
        assert "idx_order_portfolio_status_ts" in _index_names(Order)

    def test_created_desc_index(self):
        assert "idx_order_created_desc" in _index_names(Order)


class TestTradeCheckLogIndexes:
    def test_portfolio_time_index(self):
        assert "idx_tradecheck_portfolio_time" in _index_names(TradeCheckLog)


class TestAlertLogIndexes:
    def test_portfolio_created_index(self):
        assert "idx_alert_portfolio_created" in _index_names(AlertLog)

    def test_severity_created_index(self):
        assert "idx_alert_severity_created" in _index_names(AlertLog)


class TestRiskLimitChangeIndexes:
    def test_portfolio_time_index(self):
        assert "idx_risklimitchange_port_time" in _index_names(RiskLimitChange)


@pytest.mark.django_db
class TestMigrationsFresh:
    def test_no_pending_migrations(self):
        result = subprocess.run(
            [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"],
            capture_output=True,
            text=True,
            cwd=BACKEND_DIR,
        )
        assert result.returncode == 0, f"Pending migrations detected: {result.stdout}"
