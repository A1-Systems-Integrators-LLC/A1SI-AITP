"""Tests for task registry — maps task_type strings to executor functions."""

from unittest.mock import patch

import pytest

from core.services.task_registry import TASK_REGISTRY


class TestTaskRegistryContents:
    def test_registry_has_expected_keys(self):
        expected_keys = [
            "data_refresh",
            "regime_detection",
            "order_sync",
            "data_quality",
            "news_fetch",
            "workflow",
            "risk_monitoring",
            "db_maintenance",
        ]
        for key in expected_keys:
            assert key in TASK_REGISTRY, f"Missing registry key: {key}"

    def test_all_executors_are_callable(self):
        for key, executor in TASK_REGISTRY.items():
            assert callable(executor), f"Executor for {key} is not callable"


class TestTaskRegistryOrderSync:
    @pytest.mark.django_db
    def test_order_sync_no_open_orders(self):
        executor = TASK_REGISTRY["order_sync"]
        progress_calls = []

        def progress_cb(pct, msg):
            progress_calls.append((pct, msg))

        result = executor({}, progress_cb)
        assert result["status"] == "completed"
        assert result["synced"] == 0


class TestTaskRegistryRegimeDetection:
    def test_regime_detection_handles_import_error(self):
        executor = TASK_REGISTRY["regime_detection"]

        with patch(
            "core.services.task_registry.RegimeService",
            side_effect=ImportError("no regime module"),
            create=True,
        ), patch(
            "market.services.regime.RegimeService",
            side_effect=ImportError("no regime module"),
        ):
            result = executor({}, lambda pct, msg: None)
            assert result["status"] == "error"
            assert "error" in result


class TestTaskRegistryRiskMonitoring:
    @pytest.mark.django_db
    def test_risk_monitoring_no_portfolios(self):
        executor = TASK_REGISTRY["risk_monitoring"]
        progress_calls = []

        def progress_cb(pct, msg):
            progress_calls.append((pct, msg))

        result = executor({}, progress_cb)
        assert result["status"] == "completed"
        assert result["message"] == "No portfolios"


class TestTaskRegistryDbMaintenance:
    @pytest.mark.django_db
    def test_db_maintenance_executor_runs_integrity_check(self):
        executor = TASK_REGISTRY["db_maintenance"]
        progress_calls = []

        def progress_cb(pct, msg):
            progress_calls.append((pct, msg))

        result = executor({}, progress_cb)
        assert result["status"] == "completed"
        assert result["integrity"] == "ok"
        assert "journal_mode" in result

    @pytest.mark.django_db
    def test_db_maintenance_returns_journal_mode(self):
        executor = TASK_REGISTRY["db_maintenance"]
        result = executor({}, lambda p, m: None)
        assert result["journal_mode"] in ("delete", "wal", "truncate", "memory")
        assert result["integrity"] == "ok"

    def test_db_maintenance_in_registry(self):
        assert "db_maintenance" in TASK_REGISTRY
        assert callable(TASK_REGISTRY["db_maintenance"])
