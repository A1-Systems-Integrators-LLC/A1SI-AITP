"""Backtest comparison API tests — comparison analytics, rankings, deltas."""

import pytest

from analysis.models import BackgroundJob, BacktestResult


@pytest.mark.django_db
class TestBacktestCompare:
    def _create_result(self, strategy_name, metrics):
        job = BackgroundJob.objects.create(
            job_type="backtest", status="completed", params={},
        )
        return BacktestResult.objects.create(
            job=job,
            framework="freqtrade",
            strategy_name=strategy_name,
            symbol="BTC/USDT",
            timeframe="1h",
            metrics=metrics,
        )

    def test_compare_two_results(self, authenticated_client):
        r1 = self._create_result("StrategyA", {
            "total_return": 0.15, "sharpe_ratio": 1.5, "max_drawdown": 0.10,
            "win_rate": 0.55, "profit_factor": 1.3, "total_trades": 100,
        })
        r2 = self._create_result("StrategyB", {
            "total_return": 0.25, "sharpe_ratio": 1.2, "max_drawdown": 0.20,
            "win_rate": 0.60, "profit_factor": 1.5, "total_trades": 80,
        })

        resp = authenticated_client.get(f"/api/backtest/compare/?ids={r1.id},{r2.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "comparison" in data
        assert len(data["results"]) == 2
        assert data["comparison"]["best_strategy"] is not None
        assert len(data["comparison"]["metrics_table"]) == 6

    def test_compare_three_results(self, authenticated_client):
        r1 = self._create_result("A", {"total_return": 0.10, "sharpe_ratio": 1.0})
        r2 = self._create_result("B", {"total_return": 0.20, "sharpe_ratio": 2.0})
        r3 = self._create_result("C", {"total_return": 0.15, "sharpe_ratio": 1.5})

        resp = authenticated_client.get(
            f"/api/backtest/compare/?ids={r1.id},{r2.id},{r3.id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 3

    def test_compare_single_result_no_comparison(self, authenticated_client):
        r1 = self._create_result("Solo", {"total_return": 0.10})
        resp = authenticated_client.get(f"/api/backtest/compare/?ids={r1.id}")
        assert resp.status_code == 200
        data = resp.json()
        # Single result: returns raw list, no comparison key
        assert isinstance(data, list)
        assert len(data) == 1

    def test_compare_empty_metrics(self, authenticated_client):
        r1 = self._create_result("NoMetricsA", {})
        r2 = self._create_result("NoMetricsB", {})
        resp = authenticated_client.get(f"/api/backtest/compare/?ids={r1.id},{r2.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "comparison" in data

    def test_compare_missing_ids(self, authenticated_client):
        resp = authenticated_client.get("/api/backtest/compare/?ids=99999,99998")
        assert resp.status_code == 200
        # No results found = returns empty list
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_compare_auth_required(self):
        from django.test import Client

        client = Client()
        resp = client.get("/api/backtest/compare/?ids=1,2")
        assert resp.status_code == 403
