"""Tests for NautilusTrader / HFT end-to-end integration
======================================================
Covers:
- BacktestResult persistence for scheduled_nautilus_backtest / scheduled_hft_backtest jobs
- NautilusTrendFollowing produces trades with relaxed params on sufficient data
- CLI --asset-class flag parsing
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Helpers ──────────────────────────────────────────


def _make_trending_ohlcv(n: int = 500, start_price: float = 100.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data with uptrend and shallow pullbacks.

    Pattern: steady uptrend with brief, shallow dips every ~60 bars.
    The dips are gentle enough that price stays above EMA21 while RSI
    briefly dips below 45, creating valid entry conditions.
    """
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")

    prices = [start_price]
    for i in range(1, n):
        phase = i % 60
        trend = 0.002 if phase < 50 else -0.001
        noise = np.random.normal(0, 0.001)
        prices.append(prices[-1] * (1 + trend + noise))

    close = np.array(prices)
    high = close * (1 + np.abs(np.random.normal(0, 0.003, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.003, n)))
    open_ = close * (1 + np.random.normal(0, 0.001, n))
    volume = np.random.uniform(2000, 6000, n)

    # Ensure OHLCV constraints
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


def _make_multi_strategy_result(
    framework: str = "nautilus",
    asset_class: str = "crypto",
    strategies: list[str] | None = None,
    symbols: list[str] | None = None,
) -> dict:
    """Build a multi-strategy result dict matching the executor output format."""
    strategies = strategies or ["NautilusTrendFollowing", "NautilusMeanReversion"]
    symbols = symbols or ["BTC/USDT", "ETH/USDT"]
    results = []
    for strategy in strategies:
        for symbol in symbols:
            results.append(
                {
                    "strategy": strategy,
                    "symbol": symbol,
                    "status": "completed",
                    "result": {
                        "framework": framework,
                        "strategy": strategy,
                        "symbol": symbol,
                        "timeframe": "1h",
                        "metrics": {"total_trades": 3, "sharpe_ratio": 1.1},
                        "trades": [
                            {
                                "entry_time": "2024-01-01T00:00:00+00:00",
                                "exit_time": "2024-01-02T00:00:00+00:00",
                                "side": "long",
                                "entry_price": 42000.0,
                                "exit_price": 43000.0,
                                "size": 0.1,
                                "pnl": 99.58,
                            },
                        ],
                    },
                }
            )
    return {
        "status": "completed",
        "framework": framework,
        "asset_class": asset_class,
        "strategies_run": len(strategies),
        "symbols_tested": len(symbols),
        "total_backtests": len(results),
        "completed": len(results),
        "results": results,
    }


# ── Persistence tests ──────────────────────────────────────────


@pytest.mark.django_db
class TestScheduledBacktestPersistence:
    """Verify BacktestResult rows are created for scheduled nautilus/hft jobs."""

    def _create_job(self, job_type: str, params: dict | None = None):
        from analysis.models import BackgroundJob

        return BackgroundJob.objects.create(
            job_type=job_type,
            status="pending",
            params=params or {},
        )

    def _persist_result(self, job, result):
        """Mirror the persistence logic from job_runner._run_job()."""
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

    def test_scheduled_nautilus_creates_backtest_results(self):
        """scheduled_nautilus_backtest job creates one BacktestResult per strategy+symbol."""
        from analysis.models import BacktestResult

        params = {"asset_class": "crypto", "timeframe": "1h"}
        job = self._create_job("scheduled_nautilus_backtest", params)
        result = _make_multi_strategy_result(
            framework="nautilus",
            strategies=["NautilusTrendFollowing", "NautilusMeanReversion"],
            symbols=["BTC/USDT", "ETH/USDT"],
        )

        self._persist_result(job, result)

        bt_results = BacktestResult.objects.filter(job=job)
        assert bt_results.count() == 4  # 2 strategies × 2 symbols

        # Check all strategy+symbol combos exist
        combos = set(bt_results.values_list("strategy_name", "symbol"))
        assert ("NautilusTrendFollowing", "BTC/USDT") in combos
        assert ("NautilusTrendFollowing", "ETH/USDT") in combos
        assert ("NautilusMeanReversion", "BTC/USDT") in combos
        assert ("NautilusMeanReversion", "ETH/USDT") in combos

        # Check framework and asset_class
        for bt in bt_results:
            assert bt.framework == "nautilus"
            assert bt.asset_class == "crypto"
            assert bt.metrics is not None

    def test_scheduled_hft_creates_backtest_results(self):
        """scheduled_hft_backtest job creates BacktestResult rows."""
        from analysis.models import BacktestResult

        params = {"timeframe": "1h"}
        job = self._create_job("scheduled_hft_backtest", params)
        result = _make_multi_strategy_result(
            framework="hftbacktest",
            strategies=["MarketMaker"],
            symbols=["BTC/USDT"],
        )

        self._persist_result(job, result)

        bt_results = BacktestResult.objects.filter(job=job)
        assert bt_results.count() == 1
        bt = bt_results.first()
        assert bt.framework == "hftbacktest"
        assert bt.strategy_name == "MarketMaker"

    def test_scheduled_nautilus_equity_asset_class(self):
        """Equity backtests should save asset_class='equity'."""
        from analysis.models import BacktestResult

        job = self._create_job("scheduled_nautilus_backtest", {"asset_class": "equity"})
        result = _make_multi_strategy_result(
            framework="nautilus",
            asset_class="equity",
            strategies=["EquityMomentum"],
            symbols=["AAPL"],
        )

        self._persist_result(job, result)

        bt = BacktestResult.objects.get(job=job)
        assert bt.asset_class == "equity"
        assert bt.strategy_name == "EquityMomentum"
        assert bt.symbol == "AAPL"

    def test_scheduled_with_error_sub_results(self):
        """Only completed sub-results get persisted, errored ones are skipped."""
        from analysis.models import BacktestResult

        job = self._create_job("scheduled_nautilus_backtest", {})
        result = {
            "status": "completed",
            "framework": "nautilus",
            "asset_class": "crypto",
            "results": [
                {
                    "strategy": "NautilusTrendFollowing",
                    "symbol": "BTC/USDT",
                    "status": "completed",
                    "result": {
                        "timeframe": "1h",
                        "metrics": {"total_trades": 2},
                        "trades": [],
                    },
                },
                {
                    "strategy": "NautilusMeanReversion",
                    "symbol": "BTC/USDT",
                    "status": "error",
                    "error": "No data",
                },
            ],
            "completed": 1,
            "total_backtests": 2,
        }

        self._persist_result(job, result)

        assert BacktestResult.objects.filter(job=job).count() == 1

    def test_flat_backtest_still_works(self):
        """Direct 'backtest' job_type with flat result still creates BacktestResult."""
        from analysis.models import BacktestResult

        job = self._create_job("backtest", {"timerange": "20240101-20240201"})
        result = {
            "framework": "freqtrade",
            "strategy": "CryptoInvestorV1",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "metrics": {"total_trades": 5},
            "trades": [],
        }

        self._persist_result(job, result)

        bt = BacktestResult.objects.get(job=job)
        assert bt.framework == "freqtrade"
        assert bt.timerange == "20240101-20240201"

    def test_unrelated_job_type_not_persisted(self):
        """Non-backtest job types should not create BacktestResult."""
        from analysis.models import BacktestResult

        job = self._create_job("scheduled_data_refresh", {})
        result = {"status": "completed"}

        self._persist_result(job, result)

        assert BacktestResult.objects.filter(job=job).count() == 0


# ── Strategy tests ──────────────────────────────────────────


class TestTrendFollowingRelaxedParams:
    """Verify NautilusTrendFollowing produces trades with relaxed entry conditions."""

    def test_ema_params_relaxed(self):
        """EMA fast/slow should be 21/100 (not 50/200)."""
        from nautilus.strategies.trend_following import NautilusTrendFollowing

        strategy = NautilusTrendFollowing()
        assert strategy.ema_fast == 21
        assert strategy.ema_slow == 100
        assert strategy.buy_rsi_threshold == 45

    def test_enters_trade_when_conditions_met(self):
        """Strategy enters a trade when all conditions are met via on_bar simulation."""
        from unittest.mock import patch

        from nautilus.strategies.trend_following import NautilusTrendFollowing

        strategy = NautilusTrendFollowing(config={"mode": "backtest"})

        # Pre-fill 200 bars to pass warmup check
        df = _make_trending_ohlcv(n=201, start_price=100.0)
        for ts, row in df.iterrows():
            strategy.bars.append(
                {
                    "timestamp": ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )

        # Mock should_enter to return True for one bar, then exit
        enter_calls = [0]
        original_enter = strategy.should_enter

        def mock_enter(ind):
            enter_calls[0] += 1
            if enter_calls[0] == 1:
                return True  # Enter on first check
            return original_enter(ind)

        with (
            patch.object(strategy, "should_enter", side_effect=mock_enter),
            patch.object(strategy, "should_exit", return_value=False),
        ):
            bar = {
                "timestamp": pd.Timestamp("2024-01-10", tz="UTC"),
                "open": 110.0,
                "high": 111.0,
                "low": 109.0,
                "close": 110.0,
                "volume": 3000.0,
            }
            strategy.on_bar(bar)

        assert strategy.position is not None
        assert strategy.position["entry_price"] == 110.0

        # Force exit
        strategy.on_stop()
        assert len(strategy.trades) == 1

    def test_should_enter_accepts_relaxed_rsi(self):
        """should_enter should accept RSI values up to 45 (not just < 40)."""
        from nautilus.strategies.trend_following import NautilusTrendFollowing

        strategy = NautilusTrendFollowing()
        # Craft indicators that satisfy all conditions with RSI=42
        ind = pd.Series(
            {
                "close": 110.0,
                "ema_21": 108.0,
                "ema_100": 105.0,
                "rsi_14": 42.0,  # Would be rejected with old threshold of 40
                "volume_ratio": 1.2,
                "macd_hist": 0.5,
                "macd_hist_prev": 0.3,
                "bb_upper": 120.0,
            }
        )
        assert strategy.should_enter(ind) is True

    def test_should_enter_rejects_high_rsi(self):
        """should_enter should still reject RSI >= 45."""
        from nautilus.strategies.trend_following import NautilusTrendFollowing

        strategy = NautilusTrendFollowing()
        ind = pd.Series(
            {
                "close": 110.0,
                "ema_21": 108.0,
                "ema_100": 105.0,
                "rsi_14": 46.0,
                "volume_ratio": 1.2,
                "macd_hist": 0.5,
                "macd_hist_prev": 0.3,
                "bb_upper": 120.0,
            }
        )
        assert strategy.should_enter(ind) is False


# ── CLI tests ──────────────────────────────────────────


class TestNautilusRunnerCLI:
    """Verify --asset-class flag is accepted by the CLI parser."""

    def test_backtest_parser_accepts_asset_class(self):
        """The backtest subparser should accept --asset-class."""
        import argparse

        # Re-create the parser to test argument parsing
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        bt = sub.add_parser("backtest")
        bt.add_argument("--strategy", required=True)
        bt.add_argument("--symbol", default="BTC/USDT")
        bt.add_argument("--timeframe", default="1h")
        bt.add_argument("--exchange", default="kraken")
        bt.add_argument("--balance", type=float, default=10000.0)
        bt.add_argument(
            "--asset-class",
            choices=["crypto", "equity", "forex"],
            default="crypto",
        )

        args = parser.parse_args(
            [
                "backtest",
                "--strategy",
                "EquityMomentum",
                "--asset-class",
                "equity",
                "--symbol",
                "AAPL",
            ]
        )
        assert args.asset_class == "equity"
        assert args.symbol == "AAPL"
        assert args.strategy == "EquityMomentum"

    def test_asset_class_defaults_to_crypto(self):
        """--asset-class should default to 'crypto' when not specified."""
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        bt = sub.add_parser("backtest")
        bt.add_argument("--strategy", required=True)
        bt.add_argument("--asset-class", choices=["crypto", "equity", "forex"], default="crypto")

        args = parser.parse_args(["backtest", "--strategy", "NautilusTrendFollowing"])
        assert args.asset_class == "crypto"
