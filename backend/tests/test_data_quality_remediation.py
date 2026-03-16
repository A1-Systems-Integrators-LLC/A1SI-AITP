"""Tests for data quality auto-remediation."""

from dataclasses import dataclass
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest


@dataclass
class MockQualityReport:
    symbol: str
    timeframe: str
    exchange: str
    passed: bool
    is_stale: bool
    issues_summary: list


@pytest.mark.django_db
class TestDataQualityRemediation:
    @patch("core.platform_bridge.ensure_platform_imports")
    def test_no_stale_symbols_skips_remediation(self, mock_ensure):
        report = MockQualityReport("BTC/USDT", "1h", "kraken", True, False, [])
        with patch("common.data_pipeline.pipeline.validate_all_data", return_value=[report]):
            from core.services.task_registry import _run_data_quality
            result = _run_data_quality({}, lambda *a: None)
            assert result["status"] == "completed"
            assert result["quality_summary"]["remediated"] == 0

    @patch("core.platform_bridge.ensure_platform_imports")
    def test_stale_triggers_download(self, mock_ensure):
        report = MockQualityReport("BTC/USDT", "1h", "kraken", False, True, ["Stale data"])
        dl_result = {"BTC/USDT": {"status": "ok"}}
        with (
            patch("common.data_pipeline.pipeline.validate_all_data", return_value=[report]),
            patch(
                "common.data_pipeline.pipeline.download_watchlist",
                return_value=dl_result,
            ) as mock_dl,
        ):
            from core.services.task_registry import _run_data_quality
            result = _run_data_quality({}, lambda *a: None)
            assert result["quality_summary"]["remediated"] == 1
            mock_dl.assert_called_once()

    @patch("core.platform_bridge.ensure_platform_imports")
    def test_stale_cap_at_20(self, mock_ensure):
        reports = [
            MockQualityReport(f"SYM{i}/USDT", "1h", "kraken", False, True, ["Stale"])
            for i in range(30)
        ]
        with (
            patch("common.data_pipeline.pipeline.validate_all_data", return_value=reports),
            patch("common.data_pipeline.pipeline.download_watchlist", return_value={}) as mock_dl,
        ):
            from core.services.task_registry import _run_data_quality
            _run_data_quality({}, lambda *a: None)
            # Should only download up to 20 symbols total
            total_symbols = sum(
                len(call.kwargs.get("symbols", call.args[0] if call.args else []))
                for call in mock_dl.call_args_list
            )
            assert total_symbols <= 20

    @patch("core.platform_bridge.ensure_platform_imports")
    def test_download_failure_graceful(self, mock_ensure):
        report = MockQualityReport("BTC/USDT", "1h", "kraken", False, True, ["Stale"])
        with (
            patch("common.data_pipeline.pipeline.validate_all_data", return_value=[report]),
            patch(
                "common.data_pipeline.pipeline.download_watchlist",
                side_effect=Exception("network error"),
            ),
        ):
                from core.services.task_registry import _run_data_quality
                result = _run_data_quality({}, lambda *a: None)
                assert result["status"] == "completed"
                assert result["quality_summary"]["remediated"] == 0

    def test_infer_asset_class_crypto(self):
        from core.services.task_registry import _infer_asset_class
        assert _infer_asset_class("BTC/USDT", "kraken") == "crypto"

    def test_infer_asset_class_forex(self):
        from core.services.task_registry import _infer_asset_class
        assert _infer_asset_class("EUR/USD", "yfinance") == "forex"

    def test_infer_asset_class_equity(self):
        from core.services.task_registry import _infer_asset_class
        assert _infer_asset_class("AAPL", "yfinance") == "equity"

    def test_infer_asset_class_forex_from_symbol(self):
        from core.services.task_registry import _infer_asset_class
        assert _infer_asset_class("EUR/GBP", "") == "forex"


class TestForwardFillGaps:
    def test_fills_small_gaps(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from common.data_pipeline.pipeline import forward_fill_gaps

        dates = pd.date_range("2025-01-01", periods=10, freq="1h")
        df = pd.DataFrame({
            "close": [1.0, 2.0, np.nan, 4.0, 5.0, np.nan, np.nan, 8.0, 9.0, 10.0],
        }, index=dates)
        result = forward_fill_gaps(df, max_gap_bars=3)
        assert result["close"].isna().sum() == 0

    def test_does_not_fill_large_gaps(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from common.data_pipeline.pipeline import forward_fill_gaps

        dates = pd.date_range("2025-01-01", periods=10, freq="1h")
        df = pd.DataFrame({
            "close": [1.0, np.nan, np.nan, np.nan, np.nan, 6.0, 7.0, 8.0, 9.0, 10.0],
        }, index=dates)
        result = forward_fill_gaps(df, max_gap_bars=2)
        # Should have filled 2 but left 2 NaN
        assert result["close"].isna().sum() > 0

    def test_empty_df_returns_empty(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from common.data_pipeline.pipeline import forward_fill_gaps

        result = forward_fill_gaps(pd.DataFrame())
        assert result.empty

    def test_no_gaps_unchanged(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from common.data_pipeline.pipeline import forward_fill_gaps

        dates = pd.date_range("2025-01-01", periods=5, freq="1h")
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0]}, index=dates)
        result = forward_fill_gaps(df)
        pd.testing.assert_frame_equal(result, df)
