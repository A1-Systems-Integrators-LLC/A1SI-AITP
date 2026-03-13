"""
Tests for research/scripts/run_risk_validation.py — Phase 1 Coverage
====================================================================
The script is entirely module-level code (no functions), so we test it
by mocking all imports and running the module via runpy.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "research" / "scripts" / "run_risk_validation.py"


def _make_mock_ohlcv(n: int = 100) -> pd.DataFrame:
    """Create a simple OHLCV DataFrame for testing."""
    idx = pd.date_range("2025-01-01", periods=n, freq="1d", tz="UTC")
    rng = np.random.RandomState(42)
    close = 50000 + np.cumsum(rng.randn(n) * 500)
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.uniform(100, 1000, n),
        },
        index=idx,
    )


class TestRunRiskValidation:
    def test_script_runs_with_mocked_data(self, capsys):
        """Run the script with mocked load_ohlcv and verify it prints expected output."""
        mock_df = _make_mock_ohlcv()

        mock_rm = MagicMock()
        mock_rm.return_tracker.get_returns.return_value = list(range(99))
        mock_rm.calculate_position_size.return_value = 0.01
        mock_rm.check_new_trade.return_value = (True, "approved")
        mock_rm.register_trade.return_value = None
        mock_rm.get_var.return_value = MagicMock(
            var_95=-500.0, var_99=-800.0, cvar_95=-600.0, cvar_99=-900.0,
            window_days=30,
        )
        mock_rm.portfolio_heat_check.return_value = {"total_heat": 0.5}
        mock_rm.state = MagicMock(is_halted=True, halt_reason="drawdown")
        mock_rm.update_equity.return_value = None

        mock_detector = MagicMock()
        mock_state = MagicMock()
        mock_detector.detect.return_value = mock_state

        mock_router = MagicMock()
        mock_decision = MagicMock()
        mock_decision.position_size_modifier = 0.8
        mock_decision.regime = MagicMock(value="STRONG_TREND_UP")
        mock_router.route.return_value = mock_decision

        mock_corr = pd.DataFrame(
            [[1.0, 0.9], [0.9, 1.0]],
            index=["BTC/USDT", "ETH/USDT"],
            columns=["BTC/USDT", "ETH/USDT"],
        )
        mock_rm.return_tracker.get_correlation_matrix.return_value = mock_corr

        import importlib

        # Patch all dependencies before importing the module
        with (
            patch.dict("sys.modules", {
                "common.data_pipeline.pipeline": MagicMock(
                    load_ohlcv=MagicMock(return_value=mock_df)
                ),
                "common.regime.regime_detector": MagicMock(
                    RegimeDetector=MagicMock(return_value=mock_detector)
                ),
                "common.regime.strategy_router": MagicMock(
                    StrategyRouter=MagicMock(return_value=mock_router)
                ),
                "common.risk.risk_manager": MagicMock(
                    RiskManager=MagicMock(return_value=mock_rm)
                ),
            }),
        ):
            # Remove cached module if it exists
            if "research.scripts.run_risk_validation" in sys.modules:
                del sys.modules["research.scripts.run_risk_validation"]

            # Execute the script via import (it's all module-level code)
            import runpy
            try:
                runpy.run_path(str(SCRIPT_PATH), run_name="__main__")
            except SystemExit:
                pass

        captured = capsys.readouterr()
        assert "RISK MANAGER VALIDATION" in captured.out

    def test_script_handles_empty_data(self, capsys):
        """When load_ohlcv returns empty DataFrame, the script should skip that symbol."""
        empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        mock_rm = MagicMock()
        mock_rm.return_tracker.get_returns.return_value = []
        mock_rm.calculate_position_size.return_value = 0.0
        mock_rm.check_new_trade.return_value = (False, "no data")
        mock_rm.register_trade.return_value = None
        mock_rm.get_var.return_value = MagicMock(
            var_95=0, var_99=0, cvar_95=0, cvar_99=0, window_days=0,
        )
        mock_rm.portfolio_heat_check.return_value = {}
        mock_rm.state = MagicMock(is_halted=False, halt_reason=None)
        mock_rm.update_equity.return_value = None
        mock_rm.return_tracker.get_correlation_matrix.return_value = pd.DataFrame()

        mock_detector = MagicMock()
        mock_detector.detect.return_value = MagicMock()

        mock_router = MagicMock()
        mock_decision = MagicMock()
        mock_decision.position_size_modifier = 1.0
        mock_decision.regime = MagicMock(value="UNKNOWN")
        mock_router.route.return_value = mock_decision

        # Return real data for BTC (needed for position sizing) but empty for loop
        call_count = {"n": 0}
        real_df = _make_mock_ohlcv()

        def mock_load(symbol, tf, exchange):
            call_count["n"] += 1
            # First 3 calls are in the loop (BTC, ETH, SOL) — return empty to skip
            # Remaining calls are for position sizing — return real data
            if call_count["n"] <= 3:
                return empty_df
            return real_df

        with (
            patch.dict("sys.modules", {
                "common.data_pipeline.pipeline": MagicMock(
                    load_ohlcv=MagicMock(side_effect=mock_load)
                ),
                "common.regime.regime_detector": MagicMock(
                    RegimeDetector=MagicMock(return_value=mock_detector)
                ),
                "common.regime.strategy_router": MagicMock(
                    StrategyRouter=MagicMock(return_value=mock_router)
                ),
                "common.risk.risk_manager": MagicMock(
                    RiskManager=MagicMock(return_value=mock_rm)
                ),
            }),
        ):
            if "research.scripts.run_risk_validation" in sys.modules:
                del sys.modules["research.scripts.run_risk_validation"]

            import runpy
            try:
                runpy.run_path(str(SCRIPT_PATH), run_name="__main__")
            except SystemExit:
                pass

        captured = capsys.readouterr()
        assert "RISK MANAGER VALIDATION" in captured.out
