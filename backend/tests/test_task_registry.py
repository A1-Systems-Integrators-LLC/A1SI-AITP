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


class TestSqliteJournalModeSafeguards:
    """Regression tests: WAL mode destroyed the database 3 times in March 2026.

    WAL mode is incompatible with Docker virtiofs bind mounts because the
    SHM file uses mmap which virtiofs cannot handle across processes. This
    causes stale file descriptors and 'disk I/O error' on all queries.

    These tests ensure WAL mode is NEVER re-enabled. If any of these fail,
    DO NOT change the test — fix the code to use DELETE journal mode.
    """

    def test_pragma_sets_delete_not_wal(self):
        """core/apps.py must set journal_mode=DELETE, never WAL."""
        import inspect

        from core.apps import _set_sqlite_pragmas

        source = inspect.getsource(_set_sqlite_pragmas)
        assert "journal_mode=DELETE" in source, (
            "_set_sqlite_pragmas must set PRAGMA journal_mode=DELETE"
        )
        assert "journal_mode=WAL" not in source, (
            "_set_sqlite_pragmas must NEVER set WAL mode"
        )

    @pytest.mark.django_db
    def test_active_journal_mode_is_not_wal(self):
        """The live database connection must not be in WAL mode."""
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
        assert mode != "wal", (
            f"Database is in WAL mode ({mode}). "
            "WAL is incompatible with Docker virtiofs. Use DELETE."
        )

    @pytest.mark.django_db
    def test_no_wal_shm_files_created(self, tmp_path):
        """Verify that a fresh SQLite DB with our pragmas creates no WAL/SHM files."""
        import sqlite3

        db_path = tmp_path / "test_no_wal.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO test VALUES (1)")
        conn.commit()
        conn.close()

        wal_path = tmp_path / "test_no_wal.db-wal"
        shm_path = tmp_path / "test_no_wal.db-shm"
        assert not wal_path.exists(), "WAL file should not exist with DELETE mode"
        assert not shm_path.exists(), "SHM file should not exist with DELETE mode"

    def test_settings_scheduled_task_description_not_wal(self):
        """The db_maintenance task description must not reference WAL checkpoint."""
        from django.conf import settings

        desc = settings.SCHEDULED_TASKS["db_maintenance"]["description"]
        assert "wal" not in desc.lower(), (
            f"db_maintenance description still references WAL: {desc}"
        )
