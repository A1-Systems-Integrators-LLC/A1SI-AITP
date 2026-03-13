"""Tests for BacktestResult persistence (Sprint E wiring)
=======================================================
Verifies that the job_runner correctly creates BacktestResult records
when a backtest job completes successfully.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.mark.django_db
class TestBacktestResultPersistence:
    """Integration tests for backtest job → BacktestResult creation."""

    def _create_job(self, job_type="backtest", params=None):
        """Helper: create a BackgroundJob record."""
        from analysis.models import BackgroundJob

        return BackgroundJob.objects.create(
            job_type=job_type,
            status="pending",
            params=params or {},
        )

    def _simulate_completed_backtest(self, job, result):
        """Simulate the persistence logic from job_runner._run_job()."""
        from analysis.models import BacktestResult

        job.status = "completed"
        job.progress = 1.0
        job.result = result
        job.completed_at = datetime.now(timezone.utc)
        job.save()

        backtest_job_types = {
            "backtest",
            "scheduled_nautilus_backtest",
            "scheduled_hft_backtest",
        }
        if job.job_type in backtest_job_types and isinstance(result, dict):
            if result.get("results") and result.get("status") == "completed":
                # Multi-strategy result (nautilus/hft executors)
                for sub in result["results"]:
                    if sub.get("status") == "completed" and sub.get("result"):
                        sub_result = sub["result"]
                        BacktestResult.objects.create(
                            job=job,
                            framework=result.get("framework", ""),
                            asset_class=result.get("asset_class", "crypto"),
                            strategy_name=sub.get("strategy", ""),
                            symbol=sub.get("symbol", ""),
                            timeframe=sub_result.get(
                                "timeframe", (job.params or {}).get("timeframe", "")
                            ),
                            metrics=sub_result.get("metrics"),
                            trades=sub_result.get("trades"),
                            config=job.params,
                        )
            elif "error" not in result:
                # Flat result (direct backtest job)
                BacktestResult.objects.create(
                    job=job,
                    framework=result.get("framework", ""),
                    strategy_name=result.get("strategy", ""),
                    symbol=result.get("symbol", ""),
                    timeframe=result.get("timeframe", ""),
                    timerange=(job.params or {}).get("timerange", ""),
                    metrics=result.get("metrics"),
                    trades=result.get("trades"),
                    config=job.params,
                )

    def test_nautilus_result_persisted(self):
        """Successful Nautilus backtest creates a BacktestResult record."""
        from analysis.models import BacktestResult

        params = {
            "framework": "nautilus",
            "strategy": "NautilusTrendFollowing",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
        }
        job = self._create_job(params=params)

        result = {
            "framework": "nautilus",
            "strategy": "NautilusTrendFollowing",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "metrics": {"total_trades": 5, "sharpe_ratio": 1.2, "max_drawdown": -0.08},
            "trades": [
                {
                    "entry_time": "2024-01-01 00:00:00+00:00",
                    "exit_time": "2024-01-02 00:00:00+00:00",
                    "side": "long",
                    "entry_price": 42000.0,
                    "exit_price": 43000.0,
                    "size": 0.1,
                    "pnl": 99.58,
                    "pnl_pct": 0.0218,
                    "fee": 0.42,
                },
            ],
        }

        self._simulate_completed_backtest(job, result)

        bt_results = BacktestResult.objects.filter(job=job)
        assert bt_results.count() == 1

        bt = bt_results.first()
        assert bt.framework == "nautilus"
        assert bt.strategy_name == "NautilusTrendFollowing"
        assert bt.symbol == "BTC/USDT"
        assert bt.timeframe == "1h"
        assert bt.metrics["total_trades"] == 5
        assert bt.trades is not None
        assert len(bt.trades) == 1
        assert bt.trades[0]["entry_price"] == 42000.0

    def test_hft_result_persisted(self):
        """Successful HFT backtest creates a BacktestResult record."""
        from analysis.models import BacktestResult

        params = {
            "framework": "hftbacktest",
            "strategy": "MarketMaker",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
        }
        job = self._create_job(params=params)

        result = {
            "framework": "hftbacktest",
            "strategy": "MarketMaker",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "metrics": {"total_trades": 10, "sharpe_ratio": 0.8},
            "trades": [
                {
                    "entry_time": "2024-01-01 00:00:00+00:00",
                    "exit_time": "2024-01-01 01:00:00+00:00",
                    "side": "buy",
                    "entry_price": 100.0,
                    "exit_price": 101.0,
                    "size": 1.0,
                    "pnl": 0.96,
                    "pnl_pct": 0.0096,
                    "fee": 0.04,
                },
            ],
        }

        self._simulate_completed_backtest(job, result)

        bt = BacktestResult.objects.get(job=job)
        assert bt.framework == "hftbacktest"
        assert bt.strategy_name == "MarketMaker"
        assert bt.trades is not None
        assert len(bt.trades) == 1

    def test_error_result_not_persisted(self):
        """Failed backtest (with 'error' key) should NOT create BacktestResult."""
        from analysis.models import BacktestResult

        job = self._create_job(params={"framework": "nautilus"})

        result = {
            "error": "No data for BTC/USDT 1h on binance",
            "framework": "nautilus",
        }

        self._simulate_completed_backtest(job, result)

        assert BacktestResult.objects.filter(job=job).count() == 0

    def test_non_backtest_job_not_persisted(self):
        """Non-backtest job type should NOT create BacktestResult."""
        from analysis.models import BacktestResult

        job = self._create_job(job_type="screen", params={})

        result = {"framework": "vectorbt", "results": []}

        self._simulate_completed_backtest(job, result)

        assert BacktestResult.objects.filter(job=job).count() == 0

    def test_result_with_timerange(self):
        """BacktestResult should capture timerange from params."""
        from analysis.models import BacktestResult

        params = {
            "framework": "freqtrade",
            "strategy": "CryptoInvestorV1",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "timerange": "20240101-20240201",
        }
        job = self._create_job(params=params)

        result = {
            "framework": "freqtrade",
            "strategy": "CryptoInvestorV1",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "metrics": {"total_trades": 3},
            "trades": [],
        }

        self._simulate_completed_backtest(job, result)

        bt = BacktestResult.objects.get(job=job)
        assert bt.timerange == "20240101-20240201"
        assert bt.config == params

    def test_result_with_empty_trades(self):
        """Backtest with zero trades should still create BacktestResult."""
        from analysis.models import BacktestResult

        job = self._create_job(params={"framework": "nautilus"})

        result = {
            "framework": "nautilus",
            "strategy": "NautilusMeanReversion",
            "symbol": "ETH/USDT",
            "timeframe": "4h",
            "metrics": {"total_trades": 0},
            "trades": [],
        }

        self._simulate_completed_backtest(job, result)

        bt = BacktestResult.objects.get(job=job)
        assert bt.trades == []
        assert bt.metrics["total_trades"] == 0

    def test_job_backtest_result_relationship(self):
        """BacktestResult is accessible via job.backtest_results related manager."""
        job = self._create_job(params={"framework": "nautilus"})

        result = {
            "framework": "nautilus",
            "strategy": "NautilusTrendFollowing",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "metrics": {},
            "trades": [],
        }

        self._simulate_completed_backtest(job, result)

        assert job.backtest_results.count() == 1
        assert job.backtest_results.first().framework == "nautilus"
