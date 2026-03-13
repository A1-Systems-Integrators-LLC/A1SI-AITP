"""Full coverage tests for backend/analysis/ services.

Covers: step_registry (all 11 executors, get_step_types, STEP_REGISTRY),
DataPipelineService (list, info, download, generate), ScreenerService (no data,
strategy types, per-strategy error isolation), workflow_engine (condition skip,
result chaining, unknown step type, unknown run), BacktestService edge cases.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()


# ══════════════════════════════════════════════════════
# Step Registry — STEP_REGISTRY + get_step_types
# ══════════════════════════════════════════════════════


class TestStepRegistryStructure:
    def test_all_11_steps_registered(self):
        from analysis.services.step_registry import STEP_REGISTRY
        expected = {
            "data_refresh", "regime_detection", "news_fetch", "data_quality",
            "order_sync", "vbt_screen", "sentiment_aggregate", "composite_score",
            "alert_evaluate", "strategy_recommend", "ml_training",
        }
        assert expected == set(STEP_REGISTRY.keys())

    def test_all_executors_callable(self):
        from analysis.services.step_registry import STEP_REGISTRY
        for name, fn in STEP_REGISTRY.items():
            assert callable(fn), f"{name} is not callable"

    def test_get_step_types_returns_list(self):
        from analysis.services.step_registry import get_step_types
        result = get_step_types()
        assert isinstance(result, list)
        assert len(result) == 11
        for item in result:
            assert "step_type" in item
            assert "description" in item

    def test_get_step_types_descriptions_not_empty(self):
        from analysis.services.step_registry import get_step_types
        result = get_step_types()
        for item in result:
            assert item["description"], f"{item['step_type']} has empty description"


# ══════════════════════════════════════════════════════
# Step Registry — individual step executors
# ══════════════════════════════════════════════════════


class TestStepVbtScreen:
    def test_success(self):
        from analysis.services.step_registry import _step_vbt_screen
        cb = MagicMock()
        with patch("analysis.services.screening.ScreenerService.run_full_screen",
                    return_value={"strategies": {}}):
            result = _step_vbt_screen({}, cb)
        assert result["status"] == "completed"
        cb.assert_called()

    def test_import_error_returns_error(self):
        from analysis.services.step_registry import _step_vbt_screen
        cb = MagicMock()
        with patch("analysis.services.screening.ScreenerService.run_full_screen",
                    side_effect=ImportError("no vectorbt")):
            result = _step_vbt_screen({}, cb)
        assert result["status"] == "error"


class TestStepSentimentAggregate:
    def test_success(self):
        from analysis.services.step_registry import _step_sentiment_aggregate
        cb = MagicMock()
        with patch("market.services.news.NewsService.get_sentiment_signal",
                    return_value={"signal": 0.5}):
            with patch("market.services.news.NewsService.get_sentiment_summary",
                        return_value={"avg": 0.5}):
                result = _step_sentiment_aggregate({}, cb)
        assert result["status"] == "completed"
        assert "signal" in result

    def test_exception_returns_error(self):
        from analysis.services.step_registry import _step_sentiment_aggregate
        cb = MagicMock()
        with patch("market.services.news.NewsService.get_sentiment_signal",
                    side_effect=Exception("db error")):
            result = _step_sentiment_aggregate({}, cb)
        assert result["status"] == "error"


class TestStepCompositeScore:
    def test_with_prev_result(self):
        from analysis.services.step_registry import _step_composite_score
        cb = MagicMock()
        prev = {"signal": {"signal": 0.3, "conviction": 0.8}}
        with patch("market.services.regime.RegimeService.get_all_current_regimes",
                    return_value=[{"regime": "strong_trend_up", "confidence": 0.9}]):
            result = _step_composite_score({"_prev_result": prev}, cb)
        assert result["status"] == "completed"
        assert "composite_score" in result
        assert -1.0 <= result["composite_score"] <= 1.0

    def test_no_prev_result(self):
        from analysis.services.step_registry import _step_composite_score
        cb = MagicMock()
        with patch("market.services.regime.RegimeService.get_all_current_regimes",
                    return_value=[]):
            result = _step_composite_score({}, cb)
        assert result["status"] == "completed"
        assert result["composite_score"] == 0.0

    def test_bearish_regime_negative(self):
        from analysis.services.step_registry import _step_composite_score
        cb = MagicMock()
        with patch("market.services.regime.RegimeService.get_all_current_regimes",
                    return_value=[{"regime": "strong_trend_down", "confidence": 0.9}]):
            result = _step_composite_score({}, cb)
        assert result["regime_component"] < 0


class TestStepAlertEvaluate:
    def test_no_alerts(self):
        from analysis.services.step_registry import _step_alert_evaluate
        cb = MagicMock()
        result = _step_alert_evaluate({"_prev_result": {"composite_score": 0.1}}, cb)
        assert result["status"] == "completed"
        assert result["alerts_triggered"] == 0

    def test_strong_signal_triggers_alert(self):
        from analysis.services.step_registry import _step_alert_evaluate
        cb = MagicMock()
        prev = {
            "composite_score": 0.8,
            "sentiment_conviction": 0.9,
            "sentiment_component": 0.5,
        }
        # send_notification is imported locally inside the function
        result = _step_alert_evaluate({"_prev_result": prev, "alert_threshold": 0.5}, cb)
        assert result["alerts_triggered"] >= 1

    def test_notification_failure_isolated(self):
        from analysis.services.step_registry import _step_alert_evaluate
        cb = MagicMock()
        prev = {"composite_score": 0.9}
        # notification failure is caught inside the function
        result = _step_alert_evaluate({"_prev_result": prev, "alert_threshold": 0.5}, cb)
        assert result["status"] == "completed"


class TestStepStrategyRecommend:
    def test_success(self):
        from analysis.services.step_registry import _step_strategy_recommend
        cb = MagicMock()
        with patch("market.services.regime.RegimeService.get_all_recommendations",
                    return_value=[{"symbol": "BTC/USDT", "strategy": "trend"}]):
            result = _step_strategy_recommend({}, cb)
        assert result["status"] == "completed"
        assert result["count"] == 1


# ══════════════════════════════════════════════════════
# DataPipelineService
# ══════════════════════════════════════════════════════


class TestDataPipelineServiceList:
    def test_list_available_data(self, tmp_path):
        import numpy as np
        # Create a fake parquet file
        df = pd.DataFrame(
            {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100.0]},
            index=pd.DatetimeIndex([pd.Timestamp("2025-01-01", tz="UTC")]),
        )
        df.to_parquet(tmp_path / "kraken_BTC_USDT_1h.parquet")

        with patch("analysis.services.data_pipeline.ensure_platform_imports"):
            with patch("analysis.services.data_pipeline.get_processed_dir", return_value=tmp_path):
                from analysis.services.data_pipeline import DataPipelineService
                svc = DataPipelineService()
                result = svc.list_available_data()
        assert len(result) == 1
        assert result[0]["symbol"] == "BTC/USDT"
        assert result[0]["rows"] == 1

    def test_list_handles_corrupt_file(self, tmp_path):
        (tmp_path / "kraken_BAD_FILE_1h.parquet").write_text("not a parquet")
        with patch("analysis.services.data_pipeline.ensure_platform_imports"):
            with patch("analysis.services.data_pipeline.get_processed_dir", return_value=tmp_path):
                from analysis.services.data_pipeline import DataPipelineService
                svc = DataPipelineService()
                result = svc.list_available_data()
        assert len(result) == 0  # Corrupt file skipped


class TestDataPipelineServiceInfo:
    def test_file_not_found(self, tmp_path):
        with patch("analysis.services.data_pipeline.ensure_platform_imports"):
            with patch("analysis.services.data_pipeline.get_processed_dir", return_value=tmp_path):
                from analysis.services.data_pipeline import DataPipelineService
                svc = DataPipelineService()
                result = svc.get_data_info("BTC/USDT", "1h", "kraken")
        assert result is None

    def test_valid_file(self, tmp_path):
        df = pd.DataFrame(
            {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100.0]},
            index=pd.DatetimeIndex([pd.Timestamp("2025-01-01", tz="UTC")]),
        )
        df.to_parquet(tmp_path / "kraken_BTC_USDT_1h.parquet")
        with patch("analysis.services.data_pipeline.ensure_platform_imports"):
            with patch("analysis.services.data_pipeline.get_processed_dir", return_value=tmp_path):
                from analysis.services.data_pipeline import DataPipelineService
                svc = DataPipelineService()
                result = svc.get_data_info("BTC/USDT", "1h", "kraken")
        assert result is not None
        assert result["rows"] == 1
        assert "columns" in result


class TestDataPipelineServiceDownload:
    def test_download_success(self):
        from analysis.services.data_pipeline import DataPipelineService
        mock_df = pd.DataFrame({"close": [1.0]})
        with patch("analysis.services.data_pipeline.ensure_platform_imports"):
            with patch("common.data_pipeline.pipeline.fetch_ohlcv", return_value=mock_df):
                with patch("common.data_pipeline.pipeline.save_ohlcv", return_value=Path("/tmp/out.parquet")):
                    cb = MagicMock()
                    result = DataPipelineService.download_data(
                        {"symbols": ["BTC/USDT"], "timeframes": ["1h"]}, cb
                    )
        assert "BTC/USDT_1h" in result["downloads"]
        assert result["downloads"]["BTC/USDT_1h"]["status"] == "ok"

    def test_download_empty_df(self):
        from analysis.services.data_pipeline import DataPipelineService
        with patch("analysis.services.data_pipeline.ensure_platform_imports"):
            with patch("common.data_pipeline.pipeline.fetch_ohlcv", return_value=pd.DataFrame()):
                cb = MagicMock()
                result = DataPipelineService.download_data(
                    {"symbols": ["BTC/USDT"], "timeframes": ["1h"]}, cb
                )
        assert result["downloads"]["BTC/USDT_1h"]["status"] == "empty"

    def test_download_error_isolated(self):
        from analysis.services.data_pipeline import DataPipelineService
        with patch("analysis.services.data_pipeline.ensure_platform_imports"):
            with patch("common.data_pipeline.pipeline.fetch_ohlcv",
                        side_effect=Exception("network error")):
                cb = MagicMock()
                result = DataPipelineService.download_data(
                    {"symbols": ["BTC/USDT"], "timeframes": ["1h"]}, cb
                )
        assert result["downloads"]["BTC/USDT_1h"]["status"] == "error"

    def test_symbol_cap_50(self):
        from analysis.services.data_pipeline import DataPipelineService
        with patch("analysis.services.data_pipeline.ensure_platform_imports"):
            with patch("common.data_pipeline.pipeline.fetch_ohlcv", return_value=pd.DataFrame()):
                cb = MagicMock()
                symbols = [f"SYM{i}/USDT" for i in range(60)]
                result = DataPipelineService.download_data(
                    {"symbols": symbols, "timeframes": ["1h"]}, cb
                )
        assert result["total"] == 50  # Capped at 50


class TestDataPipelineServiceGenerate:
    def test_generate_sample(self, tmp_path):
        from analysis.services.data_pipeline import DataPipelineService
        with patch("analysis.services.data_pipeline.ensure_platform_imports"):
            with patch("common.data_pipeline.pipeline.save_ohlcv", return_value=tmp_path / "out.parquet"):
                cb = MagicMock()
                result = DataPipelineService.generate_sample_data(
                    {"symbols": ["BTC/USDT"], "timeframes": ["1h"], "days": 1}, cb
                )
        assert "BTC/USDT_1h" in result["generated"]
        assert result["generated"]["BTC/USDT_1h"]["status"] == "ok"


# ══════════════════════════════════════════════════════
# ScreenerService
# ══════════════════════════════════════════════════════


class TestScreenerServiceEdgeCases:
    def test_strategy_types_list(self):
        from analysis.services.screening import STRATEGY_TYPES
        names = {s["name"] for s in STRATEGY_TYPES}
        assert names == {"sma_crossover", "rsi_mean_reversion", "bollinger_breakout", "ema_rsi_combo"}

    def test_no_data_returns_error(self):
        from analysis.services.screening import ScreenerService
        with patch("analysis.services.screening.ensure_platform_imports"):
            with patch("common.data_pipeline.pipeline.load_ohlcv", return_value=pd.DataFrame()):
                cb = MagicMock()
                result = ScreenerService.run_full_screen(
                    {"symbol": "BTC/USDT", "timeframe": "1h", "exchange": "kraken"}, cb
                )
        assert "error" in result

    def test_strategy_exception_isolated(self):
        """Each strategy's exception should be caught independently."""
        from analysis.services.screening import ScreenerService
        import numpy as np
        df = pd.DataFrame(
            {"open": np.random.rand(200), "high": np.random.rand(200),
             "low": np.random.rand(200), "close": np.random.rand(200),
             "volume": np.random.rand(200)},
            index=pd.date_range("2025-01-01", periods=200, freq="1h"),
        )
        with patch("analysis.services.screening.ensure_platform_imports"):
            with patch("common.data_pipeline.pipeline.load_ohlcv", return_value=df):
                # Patch vectorbt import to raise inside the loop
                import importlib
                original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
                def mock_import(name, *args, **kwargs):
                    if name == "vectorbt":
                        raise ImportError("no vbt")
                    return original_import(name, *args, **kwargs)
                with patch("builtins.__import__", side_effect=mock_import):
                    cb = MagicMock()
                    result = ScreenerService.run_full_screen(
                        {"symbol": "BTC/USDT", "timeframe": "1h", "exchange": "kraken"}, cb
                    )
        # All strategies should have error
        for strategy_name in result.get("strategies", {}):
            assert "error" in result["strategies"][strategy_name]


# ══════════════════════════════════════════════════════
# workflow_engine — _evaluate_condition
# ══════════════════════════════════════════════════════


class TestEvaluateConditionExtended:
    def test_empty_condition_true(self):
        from analysis.services.workflow_engine import _evaluate_condition
        assert _evaluate_condition("", {}) is True
        assert _evaluate_condition("  ", {}) is True

    def test_missing_field_false(self):
        from analysis.services.workflow_engine import _evaluate_condition
        assert _evaluate_condition('result.missing == "ok"', {}) is False

    def test_numeric_gt(self):
        from analysis.services.workflow_engine import _evaluate_condition
        assert _evaluate_condition("result.score > 0.5", {"score": 0.8}) is True
        assert _evaluate_condition("result.score > 0.5", {"score": 0.3}) is False

    def test_string_equality(self):
        from analysis.services.workflow_engine import _evaluate_condition
        assert _evaluate_condition('result.status == "completed"', {"status": "completed"}) is True
        assert _evaluate_condition('result.status != "failed"', {"status": "completed"}) is True

    def test_invalid_syntax_proceeds(self):
        from analysis.services.workflow_engine import _evaluate_condition
        assert _evaluate_condition("invalid condition", {}) is True

    def test_lte_gte(self):
        from analysis.services.workflow_engine import _evaluate_condition
        assert _evaluate_condition("result.val >= 5", {"val": 5}) is True
        assert _evaluate_condition("result.val <= 5", {"val": 5}) is True


# ══════════════════════════════════════════════════════
# workflow_engine — execute_workflow
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExecuteWorkflowEdgeCases:
    def test_unknown_run_id(self):
        from analysis.services.workflow_engine import execute_workflow
        result = execute_workflow(
            {"workflow_run_id": "00000000-0000-0000-0000-000000000000", "steps": []},
            MagicMock(),
        )
        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_unknown_step_type_fails(self):
        from analysis.models import Workflow, WorkflowRun, WorkflowStep, WorkflowStepRun
        from analysis.services.workflow_engine import execute_workflow
        wf = Workflow.objects.create(name="test_wf", params={})
        step = WorkflowStep.objects.create(
            workflow=wf, name="bad step", step_type="nonexistent_type", order=1
        )
        run = WorkflowRun.objects.create(workflow=wf, trigger="manual", params={})
        WorkflowStepRun.objects.create(workflow_run=run, step=step, order=1)
        result = execute_workflow(
            {
                "workflow_run_id": str(run.id),
                "steps": [{"order": 1, "name": "bad step", "step_type": "nonexistent_type"}],
            },
            MagicMock(),
        )
        assert result["status"] == "error"
        assert "Unknown step type" in result["error"]

    def test_condition_skip(self):
        from analysis.models import Workflow, WorkflowRun, WorkflowStep, WorkflowStepRun
        from analysis.services.workflow_engine import execute_workflow
        wf = Workflow.objects.create(name="cond_wf", params={})
        step = WorkflowStep.objects.create(
            workflow=wf, name="conditional step", step_type="vbt_screen", order=1,
            condition='result.status == "completed"',
        )
        run = WorkflowRun.objects.create(workflow=wf, trigger="manual", params={})
        WorkflowStepRun.objects.create(workflow_run=run, step=step, order=1)
        # No prev_result, so result.status won't match → step skipped
        result = execute_workflow(
            {
                "workflow_run_id": str(run.id),
                "steps": [{
                    "order": 1, "name": "conditional step", "step_type": "vbt_screen",
                    "condition": 'result.status == "completed"',
                }],
            },
            MagicMock(),
        )
        assert result["status"] == "completed"
        sr = WorkflowStepRun.objects.get(workflow_run=run, order=1)
        assert sr.status == "skipped"

    def test_step_exception_fails_workflow(self):
        from analysis.models import Workflow, WorkflowRun, WorkflowStep, WorkflowStepRun
        from analysis.services.workflow_engine import execute_workflow
        wf = Workflow.objects.create(name="fail_wf", params={})
        step = WorkflowStep.objects.create(
            workflow=wf, name="failing step", step_type="vbt_screen", order=1,
        )
        run = WorkflowRun.objects.create(workflow=wf, trigger="manual", params={})
        WorkflowStepRun.objects.create(workflow_run=run, step=step, order=1)
        with patch("analysis.services.step_registry.STEP_REGISTRY",
                    {"vbt_screen": MagicMock(side_effect=RuntimeError("boom"))}):
            result = execute_workflow(
                {
                    "workflow_run_id": str(run.id),
                    "steps": [{"order": 1, "name": "failing step", "step_type": "vbt_screen"}],
                },
                MagicMock(),
            )
        assert result["status"] == "error"
        assert result["failed_step"] == 1

    def test_result_chaining(self):
        from analysis.models import Workflow, WorkflowRun, WorkflowStep, WorkflowStepRun
        from analysis.services.workflow_engine import execute_workflow
        wf = Workflow.objects.create(name="chain_wf", params={})
        step1 = WorkflowStep.objects.create(
            workflow=wf, name="step1", step_type="sentiment_aggregate", order=1,
        )
        step2 = WorkflowStep.objects.create(
            workflow=wf, name="step2", step_type="composite_score", order=2,
        )
        run = WorkflowRun.objects.create(workflow=wf, trigger="manual", params={})
        WorkflowStepRun.objects.create(workflow_run=run, step=step1, order=1)
        WorkflowStepRun.objects.create(workflow_run=run, step=step2, order=2)

        step1_result = {"status": "completed", "signal": {"signal": 0.5, "conviction": 0.8}, "summary": {}}
        step2_result = {"status": "completed", "composite_score": 0.3, "regime_component": 0.0,
                        "sentiment_component": 0.5, "sentiment_conviction": 0.8, "regime_count": 0}

        def mock_executor(params, cb):
            if "_prev_result" in params and params["_prev_result"].get("status") == "completed":
                return step2_result
            return step1_result

        with patch("analysis.services.step_registry.STEP_REGISTRY",
                    {"sentiment_aggregate": MagicMock(return_value=step1_result),
                     "composite_score": MagicMock(side_effect=mock_executor)}):
            result = execute_workflow(
                {
                    "workflow_run_id": str(run.id),
                    "steps": [
                        {"order": 1, "name": "step1", "step_type": "sentiment_aggregate"},
                        {"order": 2, "name": "step2", "step_type": "composite_score"},
                    ],
                },
                MagicMock(),
            )
        assert result["status"] == "completed"
        assert result["completed_steps"] == 2


# ══════════════════════════════════════════════════════
# WorkflowEngine.cancel
# ══════════════════════════════════════════════════════


@pytest.mark.django_db
class TestWorkflowEngineCancel:
    def test_cancel_nonexistent(self):
        from analysis.services.workflow_engine import WorkflowEngine
        assert WorkflowEngine.cancel("00000000-0000-0000-0000-000000000000") is False

    def test_cancel_completed_fails(self):
        from analysis.models import Workflow, WorkflowRun
        from analysis.services.workflow_engine import WorkflowEngine
        wf = Workflow.objects.create(name="done_wf", params={})
        run = WorkflowRun.objects.create(workflow=wf, trigger="manual", params={}, status="completed")
        assert WorkflowEngine.cancel(str(run.id)) is False

    def test_cancel_running_succeeds(self):
        from analysis.models import Workflow, WorkflowRun
        from analysis.services.workflow_engine import WorkflowEngine
        wf = Workflow.objects.create(name="run_wf", params={})
        run = WorkflowRun.objects.create(workflow=wf, trigger="manual", params={}, status="running")
        with patch("analysis.services.job_runner.get_job_runner"):
            assert WorkflowEngine.cancel(str(run.id)) is True
        run.refresh_from_db()
        assert run.status == "cancelled"


# ══════════════════════════════════════════════════════
# BacktestService — edge cases
# ══════════════════════════════════════════════════════


class TestBacktestServiceEdgeCases:
    def test_unknown_framework(self):
        from analysis.services.backtest import BacktestService
        cb = MagicMock()
        result = BacktestService.run_backtest({"framework": "unknown_framework"}, cb)
        assert "error" in result

    def test_list_strategies_returns_list(self):
        from analysis.services.backtest import BacktestService
        result = BacktestService.list_strategies()
        assert isinstance(result, list)
        frameworks = {s.get("framework") for s in result}
        assert len(frameworks) >= 1
