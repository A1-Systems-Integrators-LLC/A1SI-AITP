"""Tests for research/scripts/pipeline_report.py — Phase 1 Coverage
================================================================
Covers: collect_data_summary, collect_vbt_screening, collect_gate_validation,
collect_freqtrade_backtests, build_report, main.
"""

import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.scripts.pipeline_report import (
    build_report,
    collect_data_summary,
    collect_freqtrade_backtests,
    collect_gate_validation,
    collect_vbt_screening,
    main,
)

# ── collect_data_summary ─────────────────────────────────────


class TestCollectDataSummary:
    def test_returns_dict_with_total_files(self, tmp_path):
        # Create fake parquet files
        (tmp_path / "BTC_USDT_1h.parquet").write_bytes(b"x" * 1024)
        (tmp_path / "ETH_USDT_1h.parquet").write_bytes(b"x" * 512)

        with patch("research.scripts.pipeline_report.DATA_DIR", tmp_path):
            result = collect_data_summary()

        assert result["total_files"] == 2
        assert len(result["files"]) == 2

    def test_file_size_in_kb(self, tmp_path):
        (tmp_path / "test.parquet").write_bytes(b"x" * 2048)

        with patch("research.scripts.pipeline_report.DATA_DIR", tmp_path):
            result = collect_data_summary()

        assert result["files"][0]["name"] == "test.parquet"
        assert result["files"][0]["size_kb"] == 2.0

    def test_empty_directory(self, tmp_path):
        with patch("research.scripts.pipeline_report.DATA_DIR", tmp_path):
            result = collect_data_summary()

        assert result["total_files"] == 0
        assert result["files"] == []


# ── collect_vbt_screening ────────────────────────────────────


class TestCollectVBTScreening:
    def test_collects_summary_json(self, tmp_path):
        symbol_dir = tmp_path / "BTC_USDT_1h_20260101"
        symbol_dir.mkdir()
        summary = {"sma_crossover": {"top_sharpe": 1.5, "top_return": 0.1}}
        (symbol_dir / "summary.json").write_text(json.dumps(summary))

        with patch("research.scripts.pipeline_report.RESULTS_DIR", tmp_path):
            result = collect_vbt_screening()

        assert symbol_dir.name in result
        assert result[symbol_dir.name]["sma_crossover"]["top_sharpe"] == 1.5

    def test_multiple_symbols(self, tmp_path):
        for sym in ["BTC", "ETH"]:
            d = tmp_path / sym
            d.mkdir()
            (d / "summary.json").write_text(json.dumps({"screen": {"val": 1}}))

        with patch("research.scripts.pipeline_report.RESULTS_DIR", tmp_path):
            result = collect_vbt_screening()

        assert len(result) == 2

    def test_no_summaries(self, tmp_path):
        with patch("research.scripts.pipeline_report.RESULTS_DIR", tmp_path):
            result = collect_vbt_screening()

        assert result == {}


# ── collect_gate_validation ──────────────────────────────────


class TestCollectGateValidation:
    def _make_validation_json(self, path: Path, strategy: str, gate2_passed: bool):
        data = {
            "strategy_name": strategy,
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "data_rows": 5000,
            "gate2": {
                "passed": gate2_passed,
                "passing_combos": 10 if gate2_passed else 0,
                "total_combos": 100,
                "best_sharpe": 1.5 if gate2_passed else 0.3,
                "best_return": 0.2 if gate2_passed else -0.1,
                "best_drawdown": 0.1,
            },
            "gate3_walkforward": {"passed": True, "oos_vs_is_ratio": 0.7},
            "gate3_perturbation": {"passed": True, "min_sharpe": 0.5},
            "overall": {"passed": gate2_passed},
        }
        path.write_text(json.dumps(data))

    def test_collects_validation_files(self, tmp_path):
        self._make_validation_json(
            tmp_path / "civ1_validation_20260101.json", "CIV1", True,
        )

        with patch("research.scripts.pipeline_report.VALIDATION_DIR", tmp_path):
            result = collect_gate_validation()

        assert "CIV1" in result
        assert result["CIV1"]["gate2_passed"] is True
        assert result["CIV1"]["gate2_passing_combos"] == 10
        assert result["CIV1"]["gate3_wf_passed"] is True
        assert result["CIV1"]["gate3_wf_oos_ratio"] == 0.7
        assert result["CIV1"]["gate3_perturb_passed"] is True
        assert result["CIV1"]["overall_passed"] is True

    def test_failed_strategy(self, tmp_path):
        self._make_validation_json(
            tmp_path / "bmr_validation_20260101.json", "BMR", False,
        )

        with patch("research.scripts.pipeline_report.VALIDATION_DIR", tmp_path):
            result = collect_gate_validation()

        assert result["BMR"]["gate2_passed"] is False
        assert result["BMR"]["overall_passed"] is False

    def test_no_validation_files(self, tmp_path):
        with patch("research.scripts.pipeline_report.VALIDATION_DIR", tmp_path):
            result = collect_gate_validation()

        assert result == {}

    def test_strategy_name_from_data(self, tmp_path):
        """strategy_name in JSON takes priority over filename."""
        data = {"strategy_name": "MyStrategy", "gate2": {}, "gate3_walkforward": {},
                "gate3_perturbation": {}, "overall": {}}
        (tmp_path / "x_validation_y.json").write_text(json.dumps(data))

        with patch("research.scripts.pipeline_report.VALIDATION_DIR", tmp_path):
            result = collect_gate_validation()

        assert "MyStrategy" in result


# ── collect_freqtrade_backtests ──────────────────────────────


class TestCollectFreqtradeBacktests:
    def _make_backtest_zip(self, dir_path: Path, filename: str, strategies: dict):
        data = {"strategy": strategies}
        zip_path = dir_path / filename
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("backtest.json", json.dumps(data))
        return zip_path

    def test_extracts_strategy_metrics(self, tmp_path):
        (tmp_path / ".last_result.json").write_text("{}")
        self._make_backtest_zip(
            tmp_path,
            "bt_20260101.zip",
            {
                "CIV1": {
                    "total_trades": 50,
                    "profit_total": 0.15,
                    "profit_total_abs": 150.0,
                    "max_drawdown_abs": 50.0,
                    "max_drawdown": 0.05,
                    "wins": 30,
                    "losses": 20,
                    "backtest_start": "2025-01-01",
                    "backtest_end": "2025-12-31",
                    "market_change": 0.10,
                },
            },
        )

        with patch("research.scripts.pipeline_report.FT_RESULTS_DIR", tmp_path):
            result = collect_freqtrade_backtests()

        assert "CIV1" in result
        assert result["CIV1"]["total_trades"] == 50
        assert result["CIV1"]["profit_total_pct"] == 15.0
        assert result["CIV1"]["profit_total_abs"] == 150.0
        assert result["CIV1"]["max_drawdown_abs"] == 50.0
        assert result["CIV1"]["max_drawdown_pct"] == 5.0
        assert result["CIV1"]["wins"] == 30
        assert result["CIV1"]["losses"] == 20
        assert result["CIV1"]["win_rate_pct"] == 60.0
        assert result["CIV1"]["market_change_pct"] == 10.0

    def test_no_last_result_returns_empty(self, tmp_path):
        with patch("research.scripts.pipeline_report.FT_RESULTS_DIR", tmp_path):
            result = collect_freqtrade_backtests()

        assert result == {}

    def test_corrupted_zip_handled(self, tmp_path):
        (tmp_path / ".last_result.json").write_text("{}")
        (tmp_path / "bad.zip").write_bytes(b"not a zip")

        with patch("research.scripts.pipeline_report.FT_RESULTS_DIR", tmp_path):
            result = collect_freqtrade_backtests()

        assert "bad" in result
        assert "error" in result["bad"]

    def test_multiple_strategies_in_zip(self, tmp_path):
        (tmp_path / ".last_result.json").write_text("{}")
        self._make_backtest_zip(
            tmp_path,
            "bt.zip",
            {
                "CIV1": {"total_trades": 10, "wins": 5, "losses": 5,
                          "profit_total": 0.05, "profit_total_abs": 50,
                          "max_drawdown_abs": 20, "max_drawdown": 0.02,
                          "market_change": 0.01},
                "BMR": {"total_trades": 20, "wins": 12, "losses": 8,
                         "profit_total": 0.08, "profit_total_abs": 80,
                         "max_drawdown_abs": 30, "max_drawdown": 0.03,
                         "market_change": 0.02},
            },
        )

        with patch("research.scripts.pipeline_report.FT_RESULTS_DIR", tmp_path):
            result = collect_freqtrade_backtests()

        assert "CIV1" in result
        assert "BMR" in result

    def test_zero_trades_win_rate(self, tmp_path):
        """Zero trades should not cause division by zero."""
        (tmp_path / ".last_result.json").write_text("{}")
        self._make_backtest_zip(
            tmp_path,
            "bt.zip",
            {"Empty": {"total_trades": 0, "wins": 0, "losses": 0,
                        "profit_total": 0, "profit_total_abs": 0,
                        "max_drawdown_abs": 0, "max_drawdown": 0,
                        "market_change": 0}},
        )

        with patch("research.scripts.pipeline_report.FT_RESULTS_DIR", tmp_path):
            result = collect_freqtrade_backtests()

        assert result["Empty"]["win_rate_pct"] == 0.0


# ── build_report ─────────────────────────────────────────────


class TestBuildReport:
    def test_report_structure(self):
        with (
            patch("research.scripts.pipeline_report.collect_data_summary",
                  return_value={"total_files": 5, "files": []}),
            patch("research.scripts.pipeline_report.collect_vbt_screening",
                  return_value={}),
            patch("research.scripts.pipeline_report.collect_gate_validation",
                  return_value={}),
            patch("research.scripts.pipeline_report.collect_freqtrade_backtests",
                  return_value={}),
        ):
            report = build_report()

        assert "pipeline_run" in report
        assert report["pipeline_run"]["platform"] == "a1si-aitp"
        assert "phase1_data" in report
        assert "phase2_vbt_screening" in report
        assert "phase3_gate_validation" in report
        assert "phase5_freqtrade_backtests" in report
        assert "summary" in report

    def test_summary_counts(self):
        gate_results = {
            "CIV1": {"gate2_passed": True, "gate3_wf_passed": "True",
                      "gate3_perturb_passed": True, "overall_passed": True},
            "BMR": {"gate2_passed": False, "gate3_wf_passed": "false",
                     "gate3_perturb_passed": False, "overall_passed": False},
        }
        ft_results = {
            "CIV1": {"total_trades": 50, "profit_total_abs": 100.0},
            "BMR": {"total_trades": 30, "profit_total_abs": -20.0},
        }

        with (
            patch("research.scripts.pipeline_report.collect_data_summary",
                  return_value={"total_files": 3, "files": []}),
            patch("research.scripts.pipeline_report.collect_vbt_screening",
                  return_value={}),
            patch("research.scripts.pipeline_report.collect_gate_validation",
                  return_value=gate_results),
            patch("research.scripts.pipeline_report.collect_freqtrade_backtests",
                  return_value=ft_results),
        ):
            report = build_report()

        s = report["summary"]
        assert s["data_files"] == 3
        assert s["strategies_validated"] == 2
        assert s["strategies_gate2_passed"] == 1
        assert s["strategies_gate3_wf_passed"] == 1
        assert s["strategies_gate3_perturb_passed"] == 1
        assert s["strategies_overall_passed"] == 1
        assert s["freqtrade_strategies_tested"] == 2
        assert s["freqtrade_total_trades"] == 80
        assert s["freqtrade_total_profit"] == 80.0


# ── main ─────────────────────────────────────────────────────


class TestMain:
    def test_saves_report_and_prints_summary(self, tmp_path, capsys):
        gate_results = {
            "CIV1": {"gate2_passed": True, "gate3_wf_passed": "True",
                      "gate3_perturb_passed": True, "overall_passed": True,
                      "gate2_best_sharpe": 1.5},
        }
        ft_results = {
            "CIV1": {"total_trades": 50, "profit_total_abs": 100.0,
                      "win_rate_pct": 60.0, "max_drawdown_abs": 20.0,
                      "market_change_pct": 5.0},
        }
        vbt_screens = {
            "BTC_USDT": {
                "sma_crossover": {"top_sharpe": 1.5, "top_return": 0.2},
            },
        }

        with (
            patch("research.scripts.pipeline_report.collect_data_summary",
                  return_value={"total_files": 2, "files": []}),
            patch("research.scripts.pipeline_report.collect_vbt_screening",
                  return_value=vbt_screens),
            patch("research.scripts.pipeline_report.collect_gate_validation",
                  return_value=gate_results),
            patch("research.scripts.pipeline_report.collect_freqtrade_backtests",
                  return_value=ft_results),
            patch("research.scripts.pipeline_report.RESULTS_DIR", tmp_path),
        ):
            main()

        captured = capsys.readouterr()
        assert "Report saved to" in captured.out
        assert "E2E PIPELINE REPORT SUMMARY" in captured.out
        assert "CIV1" in captured.out
        assert "PASS" in captured.out

        # Verify JSON file was saved
        json_files = list(tmp_path.glob("e2e_report_*.json"))
        assert len(json_files) == 1

        with open(json_files[0]) as f:
            saved = json.load(f)
        assert "summary" in saved

    def test_prints_no_valid_screens(self, tmp_path, capsys):
        """VBT screen with inf sharpe should print 'no valid screens'."""
        vbt_screens = {
            "BTC_USDT": {
                "sma_crossover": {"top_sharpe": float("inf"), "top_return": 0.0},
            },
        }

        with (
            patch("research.scripts.pipeline_report.collect_data_summary",
                  return_value={"total_files": 0, "files": []}),
            patch("research.scripts.pipeline_report.collect_vbt_screening",
                  return_value=vbt_screens),
            patch("research.scripts.pipeline_report.collect_gate_validation",
                  return_value={}),
            patch("research.scripts.pipeline_report.collect_freqtrade_backtests",
                  return_value={}),
            patch("research.scripts.pipeline_report.RESULTS_DIR", tmp_path),
        ):
            main()

        captured = capsys.readouterr()
        assert "no valid screens" in captured.out

    def test_prints_gate_fail(self, tmp_path, capsys):
        gate_results = {
            "BMR": {"gate2_passed": False, "gate3_wf_passed": False,
                     "gate3_perturb_passed": False, "overall_passed": False,
                     "gate2_best_sharpe": 0.3},
        }

        with (
            patch("research.scripts.pipeline_report.collect_data_summary",
                  return_value={"total_files": 0, "files": []}),
            patch("research.scripts.pipeline_report.collect_vbt_screening",
                  return_value={}),
            patch("research.scripts.pipeline_report.collect_gate_validation",
                  return_value=gate_results),
            patch("research.scripts.pipeline_report.collect_freqtrade_backtests",
                  return_value={}),
            patch("research.scripts.pipeline_report.RESULTS_DIR", tmp_path),
        ):
            main()

        captured = capsys.readouterr()
        assert "FAIL" in captured.out

    def test_vbt_screen_zero_sharpe(self, tmp_path, capsys):
        """VBT screen with 0 sharpe treated as no valid screen."""
        vbt_screens = {
            "BTC_USDT": {
                "sma_crossover": {"top_sharpe": 0, "top_return": 0.0},
            },
        }

        with (
            patch("research.scripts.pipeline_report.collect_data_summary",
                  return_value={"total_files": 0, "files": []}),
            patch("research.scripts.pipeline_report.collect_vbt_screening",
                  return_value=vbt_screens),
            patch("research.scripts.pipeline_report.collect_gate_validation",
                  return_value={}),
            patch("research.scripts.pipeline_report.collect_freqtrade_backtests",
                  return_value={}),
            patch("research.scripts.pipeline_report.RESULTS_DIR", tmp_path),
        ):
            main()

        captured = capsys.readouterr()
        # 0 sharpe is > -inf so should match as best_screen
        assert "BTC_USDT" in captured.out

    def test_gate_validation_none_sharpe(self, tmp_path, capsys):
        """gate2_best_sharpe=None should print N/A."""
        gate_results = {
            "Test": {"gate2_passed": False, "gate3_wf_passed": False,
                     "gate3_perturb_passed": False, "overall_passed": False,
                     "gate2_best_sharpe": None},
        }

        with (
            patch("research.scripts.pipeline_report.collect_data_summary",
                  return_value={"total_files": 0, "files": []}),
            patch("research.scripts.pipeline_report.collect_vbt_screening",
                  return_value={}),
            patch("research.scripts.pipeline_report.collect_gate_validation",
                  return_value=gate_results),
            patch("research.scripts.pipeline_report.collect_freqtrade_backtests",
                  return_value={}),
            patch("research.scripts.pipeline_report.RESULTS_DIR", tmp_path),
        ):
            main()

        captured = capsys.readouterr()
        assert "N/A" in captured.out
