"""Tests for the scheduled task system — model, service, and API."""

from unittest.mock import patch

import pytest

from core.models import ScheduledTask

# ── Model tests ─────────────────────────────────────────────


@pytest.mark.django_db
class TestScheduledTaskModel:
    def test_create_task(self):
        task = ScheduledTask.objects.create(
            id="test_task",
            name="Test Task",
            task_type="data_refresh",
            interval_seconds=3600,
            params={"asset_class": "crypto"},
        )
        assert task.id == "test_task"
        assert task.status == ScheduledTask.ACTIVE
        assert task.run_count == 0
        assert task.error_count == 0

    def test_str_representation(self):
        task = ScheduledTask.objects.create(
            id="test_str",
            name="My Task",
            task_type="data_refresh",
        )
        assert "My Task" in str(task)
        assert "data_refresh" in str(task)

    def test_default_status_is_active(self):
        task = ScheduledTask.objects.create(
            id="test_default",
            name="Default",
            task_type="test",
        )
        assert task.status == "active"

    def test_params_default_empty_dict(self):
        task = ScheduledTask.objects.create(
            id="test_params",
            name="Params Test",
            task_type="test",
        )
        assert task.params == {}

    def test_ordering_by_id(self):
        ScheduledTask.objects.create(id="z_task", name="Z", task_type="test")
        ScheduledTask.objects.create(id="a_task", name="A", task_type="test")
        tasks = list(ScheduledTask.objects.values_list("id", flat=True))
        assert tasks == ["a_task", "z_task"]


# ── Scheduler service tests ─────────────────────────────────


@pytest.mark.django_db
class TestTaskSchedulerService:
    def test_sync_tasks_to_db(self):
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        scheduler._sync_tasks_to_db()

        # Should have created tasks from SCHEDULED_TASKS setting
        assert ScheduledTask.objects.filter(id="data_refresh_crypto").exists()
        assert ScheduledTask.objects.filter(id="regime_detection").exists()
        assert ScheduledTask.objects.filter(id="news_fetch").exists()
        assert ScheduledTask.objects.count() == 7

    def test_sync_updates_existing(self):
        ScheduledTask.objects.create(
            id="data_refresh_crypto",
            name="Old Name",
            task_type="data_refresh",
            interval_seconds=999,
        )

        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        scheduler._sync_tasks_to_db()

        task = ScheduledTask.objects.get(id="data_refresh_crypto")
        assert task.name == "Crypto Data Refresh"
        assert task.interval_seconds == 3600

    def test_get_status_not_running(self):
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        scheduler._sync_tasks_to_db()
        status = scheduler.get_status()
        assert status["running"] is False
        assert status["total_tasks"] == 7

    def test_pause_task(self):
        ScheduledTask.objects.create(
            id="test_pause",
            name="Pause Test",
            task_type="test",
            interval_seconds=60,
        )
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        result = scheduler.pause_task("test_pause")
        assert result is True
        task = ScheduledTask.objects.get(id="test_pause")
        assert task.status == ScheduledTask.PAUSED
        assert task.next_run_at is None

    def test_pause_nonexistent_returns_false(self):
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        assert scheduler.pause_task("nonexistent") is False

    def test_resume_task(self):
        ScheduledTask.objects.create(
            id="test_resume",
            name="Resume Test",
            task_type="test",
            interval_seconds=60,
            status=ScheduledTask.PAUSED,
        )
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        result = scheduler.resume_task("test_resume")
        assert result is True
        task = ScheduledTask.objects.get(id="test_resume")
        assert task.status == ScheduledTask.ACTIVE

    def test_trigger_task(self):
        ScheduledTask.objects.create(
            id="test_trigger",
            name="Trigger Test",
            task_type="data_refresh",
            interval_seconds=60,
        )
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        with patch("analysis.services.job_runner.JobRunner.submit", return_value="test-job-123"):
            job_id = scheduler.trigger_task("test_trigger")
        assert job_id == "test-job-123"

        task = ScheduledTask.objects.get(id="test_trigger")
        assert task.last_run_job_id == "test-job-123"
        assert task.run_count == 1

    def test_trigger_nonexistent_returns_none(self):
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        assert scheduler.trigger_task("nonexistent") is None

    def test_trigger_unknown_task_type_returns_none(self):
        ScheduledTask.objects.create(
            id="test_unknown_type",
            name="Unknown",
            task_type="nonexistent_type",
            interval_seconds=60,
        )
        from core.services.scheduler import TaskScheduler

        scheduler = TaskScheduler()
        assert scheduler.trigger_task("test_unknown_type") is None


# ── Task registry tests ─────────────────────────────────────


class TestTaskRegistry:
    def test_registry_has_all_types(self):
        from core.services.task_registry import TASK_REGISTRY

        expected = {"data_refresh", "regime_detection", "order_sync", "data_quality", "news_fetch"}
        assert expected == set(TASK_REGISTRY.keys())

    def test_executors_are_callable(self):
        from core.services.task_registry import TASK_REGISTRY

        for name, fn in TASK_REGISTRY.items():
            assert callable(fn), f"{name} executor is not callable"


# ── API tests ────────────────────────────────────────────────


@pytest.mark.django_db
class TestSchedulerAPI:
    def test_status_requires_auth(self, api_client):
        resp = api_client.get("/api/scheduler/status/")
        assert resp.status_code == 403

    def test_status_authenticated(self, authenticated_client):
        resp = authenticated_client.get("/api/scheduler/status/")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert "total_tasks" in data

    def test_task_list(self, authenticated_client):
        ScheduledTask.objects.create(
            id="test_list",
            name="List Test",
            task_type="test",
        )
        resp = authenticated_client.get("/api/scheduler/tasks/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert any(t["id"] == "test_list" for t in data)

    def test_task_detail(self, authenticated_client):
        ScheduledTask.objects.create(
            id="test_detail",
            name="Detail Test",
            task_type="test",
            interval_seconds=300,
        )
        resp = authenticated_client.get("/api/scheduler/tasks/test_detail/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "test_detail"
        assert data["interval_seconds"] == 300

    def test_task_detail_not_found(self, authenticated_client):
        resp = authenticated_client.get("/api/scheduler/tasks/nonexistent/")
        assert resp.status_code == 404

    def test_pause_task(self, authenticated_client):
        ScheduledTask.objects.create(
            id="test_api_pause",
            name="Pause API",
            task_type="test",
        )
        resp = authenticated_client.post("/api/scheduler/tasks/test_api_pause/pause/")
        assert resp.status_code == 200
        task = ScheduledTask.objects.get(id="test_api_pause")
        assert task.status == "paused"

    def test_resume_task(self, authenticated_client):
        ScheduledTask.objects.create(
            id="test_api_resume",
            name="Resume API",
            task_type="test",
            status="paused",
        )
        resp = authenticated_client.post("/api/scheduler/tasks/test_api_resume/resume/")
        assert resp.status_code == 200
        task = ScheduledTask.objects.get(id="test_api_resume")
        assert task.status == "active"

    def test_trigger_task(self, authenticated_client):
        ScheduledTask.objects.create(
            id="test_api_trigger",
            name="Trigger API",
            task_type="data_refresh",
        )
        with patch("analysis.services.job_runner.JobRunner.submit", return_value="job-456"):
            resp = authenticated_client.post("/api/scheduler/tasks/test_api_trigger/trigger/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job-456"

    def test_trigger_not_found(self, authenticated_client):
        resp = authenticated_client.post("/api/scheduler/tasks/nonexistent/trigger/")
        assert resp.status_code == 404
