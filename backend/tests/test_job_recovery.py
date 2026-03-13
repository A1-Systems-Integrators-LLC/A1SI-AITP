"""Tests for stale job/workflow recovery on startup."""

from datetime import datetime, timezone

import pytest

from analysis.models import BackgroundJob, Workflow, WorkflowRun
from analysis.services.job_runner import recover_stale_jobs, recover_stale_workflow_runs


@pytest.mark.django_db
class TestRecoverStaleJobs:
    def test_running_jobs_marked_failed(self):
        job = BackgroundJob.objects.create(
            job_type="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        count = recover_stale_jobs()
        assert count == 1
        job.refresh_from_db()
        assert job.status == "failed"
        assert job.error == "Interrupted by server restart"
        assert job.completed_at is not None

    def test_pending_jobs_marked_failed(self):
        job = BackgroundJob.objects.create(job_type="test", status="pending")
        count = recover_stale_jobs()
        assert count == 1
        job.refresh_from_db()
        assert job.status == "failed"
        assert "restart" in job.error

    def test_completed_jobs_not_touched(self):
        job = BackgroundJob.objects.create(
            job_type="test",
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        count = recover_stale_jobs()
        assert count == 0
        job.refresh_from_db()
        assert job.status == "completed"

    def test_failed_jobs_not_touched(self):
        job = BackgroundJob.objects.create(
            job_type="test",
            status="failed",
            error="original error",
            completed_at=datetime.now(timezone.utc),
        )
        count = recover_stale_jobs()
        assert count == 0
        job.refresh_from_db()
        assert job.error == "original error"

    def test_cancelled_jobs_not_touched(self):
        job = BackgroundJob.objects.create(
            job_type="test",
            status="cancelled",
            completed_at=datetime.now(timezone.utc),
        )
        count = recover_stale_jobs()
        assert count == 0
        job.refresh_from_db()
        assert job.status == "cancelled"

    def test_multiple_stale_jobs(self):
        BackgroundJob.objects.create(job_type="a", status="running")
        BackgroundJob.objects.create(job_type="b", status="pending")
        BackgroundJob.objects.create(job_type="c", status="completed")
        count = recover_stale_jobs()
        assert count == 2

    def test_no_stale_jobs(self):
        BackgroundJob.objects.create(job_type="test", status="completed")
        count = recover_stale_jobs()
        assert count == 0


@pytest.mark.django_db
class TestRecoverStaleWorkflowRuns:
    def _create_workflow(self):
        return Workflow.objects.create(
            name="Test Workflow",
            description="test",
        )

    def test_running_workflow_runs_marked_failed(self):
        wf = self._create_workflow()
        run = WorkflowRun.objects.create(
            workflow=wf,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        count = recover_stale_workflow_runs()
        assert count == 1
        run.refresh_from_db()
        assert run.status == "failed"
        assert "restart" in run.error
        assert run.completed_at is not None

    def test_pending_workflow_runs_marked_failed(self):
        wf = self._create_workflow()
        run = WorkflowRun.objects.create(workflow=wf, status="pending")
        count = recover_stale_workflow_runs()
        assert count == 1
        run.refresh_from_db()
        assert run.status == "failed"

    def test_completed_workflow_runs_not_touched(self):
        wf = self._create_workflow()
        run = WorkflowRun.objects.create(
            workflow=wf,
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        count = recover_stale_workflow_runs()
        assert count == 0
        run.refresh_from_db()
        assert run.status == "completed"

    def test_no_stale_runs(self):
        count = recover_stale_workflow_runs()
        assert count == 0
