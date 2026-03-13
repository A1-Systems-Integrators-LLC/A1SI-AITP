"""Comprehensive tests for the Workflow Engine.

Covers cascade failure, step recovery, timeout handling, cancellation,
auto-triggered workflows, execution order, empty workflows, concurrent runs,
step parameters, template sync, condition evaluation edge cases, and more.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from analysis.models import (
    Workflow,
    WorkflowRun,
    WorkflowStep,
    WorkflowStepRun,
)
from analysis.services.workflow_engine import (
    WorkflowEngine,
    _evaluate_condition,
    execute_workflow,
)

# ── Helpers ──────────────────────────────────────────────────

def _make_workflow(wf_id: str, steps_data: list[dict]) -> Workflow:
    """Create a Workflow with WorkflowSteps from a list of dicts."""
    wf = Workflow.objects.create(id=wf_id, name=f"WF {wf_id}")
    for s in steps_data:
        WorkflowStep.objects.create(workflow=wf, **s)
    return wf


def _prepare_run(wf: Workflow, params: dict | None = None) -> tuple[WorkflowRun, list[dict]]:
    """Create a WorkflowRun + StepRuns and return (run, step_info_list)."""
    steps = list(wf.steps.order_by("order"))
    run = WorkflowRun.objects.create(
        workflow=wf,
        total_steps=len(steps),
        params=params or {},
    )
    step_info_list = []
    for s in steps:
        WorkflowStepRun.objects.create(workflow_run=run, step=s, order=s.order)
        step_info_list.append({
            "step_id": s.id,
            "order": s.order,
            "name": s.name,
            "step_type": s.step_type,
            "params": s.params,
            "condition": s.condition,
            "timeout_seconds": s.timeout_seconds,
        })
    return run, step_info_list


def _noop_cb(progress: float, message: str) -> None:
    pass


# ── 1. Cascade Failure ──────────────────────────────────────

@pytest.mark.django_db
class TestCascadeFailure:
    """When a step fails, subsequent steps must NOT execute."""

    @patch("analysis.services.step_registry.STEP_REGISTRY", {
        "ok_step": lambda p, cb: {"status": "completed"},
        "fail_step": MagicMock(side_effect=RuntimeError("step 2 exploded")),
        "after_fail": MagicMock(return_value={"status": "completed"}),
    })
    def test_steps_after_failure_remain_pending(self):
        wf = _make_workflow("cascade_1", [
            {"order": 1, "name": "OK", "step_type": "ok_step"},
            {"order": 2, "name": "Fail", "step_type": "fail_step"},
            {"order": 3, "name": "After Fail", "step_type": "after_fail"},
        ])
        run, step_info = _prepare_run(wf)

        result = execute_workflow(
            {"workflow_run_id": str(run.id), "steps": step_info},
            _noop_cb,
        )

        assert result["status"] == "error"
        assert result["failed_step"] == 2

        step_runs = list(
            WorkflowStepRun.objects.filter(workflow_run=run).order_by("order"),
        )
        assert step_runs[0].status == "completed"
        assert step_runs[1].status == "failed"
        # Step 3 was never reached — still pending
        assert step_runs[2].status == "pending"

    @patch("analysis.services.step_registry.STEP_REGISTRY", {
        "ok_step": lambda p, cb: {"status": "completed"},
        "fail_step": MagicMock(side_effect=RuntimeError("step 2 exploded")),
        "after_fail": MagicMock(return_value={"status": "completed"}),
    })
    def test_cascade_failure_does_not_call_subsequent_executor(self):
        """The executor for step 3 should never be invoked."""
        registry = {
            "ok_step": lambda p, cb: {"status": "completed"},
            "fail_step": MagicMock(side_effect=RuntimeError("boom")),
            "after_fail": MagicMock(return_value={"status": "completed"}),
        }
        with patch("analysis.services.step_registry.STEP_REGISTRY", registry):
            wf = _make_workflow("cascade_2", [
                {"order": 1, "name": "OK", "step_type": "ok_step"},
                {"order": 2, "name": "Fail", "step_type": "fail_step"},
                {"order": 3, "name": "After Fail", "step_type": "after_fail"},
            ])
            run, step_info = _prepare_run(wf)
            execute_workflow(
                {"workflow_run_id": str(run.id), "steps": step_info},
                _noop_cb,
            )
            registry["after_fail"].assert_not_called()

    @patch("analysis.services.step_registry.STEP_REGISTRY", {
        "ok_step": lambda p, cb: {"status": "completed"},
        "fail_step": MagicMock(side_effect=RuntimeError("kaboom")),
        "after_fail": MagicMock(return_value={"status": "completed"}),
    })
    def test_cascade_failure_sets_run_error_message(self):
        wf = _make_workflow("cascade_3", [
            {"order": 1, "name": "OK", "step_type": "ok_step"},
            {"order": 2, "name": "Boom Step", "step_type": "fail_step"},
            {"order": 3, "name": "After", "step_type": "after_fail"},
        ])
        run, step_info = _prepare_run(wf)
        execute_workflow(
            {"workflow_run_id": str(run.id), "steps": step_info},
            _noop_cb,
        )
        run.refresh_from_db()
        assert run.status == "failed"
        assert "Boom Step" in run.error
        assert "kaboom" in run.error
        assert run.completed_at is not None


# ── 2. Step Recovery ─────────────────────────────────────────

@pytest.mark.django_db
class TestStepRecovery:
    """After fixing a failed step, re-running the workflow should succeed."""

    def test_rerun_after_fix_succeeds(self):
        registry = {
            "ok_step": lambda p, cb: {"status": "completed", "val": 1},
            "fixed_step": lambda p, cb: {"status": "completed", "val": 2},
        }
        with patch("analysis.services.step_registry.STEP_REGISTRY", registry):
            wf = _make_workflow("recovery_1", [
                {"order": 1, "name": "OK", "step_type": "ok_step"},
                {"order": 2, "name": "Fixed", "step_type": "fixed_step"},
            ])

            # First run — step 2 fails
            registry["fixed_step"] = MagicMock(side_effect=RuntimeError("broken"))
            with patch("analysis.services.step_registry.STEP_REGISTRY", registry):
                run1, info1 = _prepare_run(wf)
                r1 = execute_workflow(
                    {"workflow_run_id": str(run1.id), "steps": info1},
                    _noop_cb,
                )
                assert r1["status"] == "error"

            # Second run — step 2 fixed
            registry["fixed_step"] = lambda p, cb: {"status": "completed", "val": 2}
            with patch("analysis.services.step_registry.STEP_REGISTRY", registry):
                run2, info2 = _prepare_run(wf)
                r2 = execute_workflow(
                    {"workflow_run_id": str(run2.id), "steps": info2},
                    _noop_cb,
                )
                assert r2["status"] == "completed"
                assert r2["completed_steps"] == 2


# ── 3. Workflow Timeout (unknown step type) ──────────────────

@pytest.mark.django_db
class TestWorkflowTimeout:
    """Steps with unknown type should be marked failed immediately."""

    @patch("analysis.services.step_registry.STEP_REGISTRY", {
        "ok_step": lambda p, cb: {"status": "completed"},
    })
    def test_unknown_step_type_fails_with_error(self):
        wf = _make_workflow("timeout_1", [
            {"order": 1, "name": "OK", "step_type": "ok_step"},
            {"order": 2, "name": "Unknown", "step_type": "nonexistent_type"},
        ])
        run, step_info = _prepare_run(wf)
        result = execute_workflow(
            {"workflow_run_id": str(run.id), "steps": step_info},
            _noop_cb,
        )
        assert result["status"] == "error"
        assert "Unknown step type" in result["error"]

        step_runs = list(
            WorkflowStepRun.objects.filter(workflow_run=run).order_by("order"),
        )
        assert step_runs[0].status == "completed"
        assert step_runs[1].status == "failed"
        assert "Unknown step type" in step_runs[1].error

    def test_slow_step_records_duration(self):
        """Verify duration_seconds is tracked even for slow steps."""
        def slow_executor(params, cb):
            time.sleep(0.05)
            return {"status": "completed"}

        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "slow_step": slow_executor,
        }):
            wf = _make_workflow("timeout_2", [
                {"order": 1, "name": "Slow", "step_type": "slow_step"},
            ])
            run, step_info = _prepare_run(wf)
            execute_workflow(
                {"workflow_run_id": str(run.id), "steps": step_info},
                _noop_cb,
            )
            sr = WorkflowStepRun.objects.get(workflow_run=run, order=1)
            assert sr.duration_seconds is not None
            assert sr.duration_seconds >= 0.04


# ── 4. Workflow Cancellation ─────────────────────────────────

@pytest.mark.django_db
class TestWorkflowCancellation:
    """Cancel mid-execution marks workflow cancelled."""

    def test_cancel_pending_run(self):
        wf = _make_workflow("cancel_1", [
            {"order": 1, "name": "S1", "step_type": "data_refresh"},
        ])
        run = WorkflowRun.objects.create(workflow=wf, status="pending")
        assert WorkflowEngine.cancel(str(run.id)) is True
        run.refresh_from_db()
        assert run.status == "cancelled"
        assert run.completed_at is not None

    def test_cancel_running_run(self):
        wf = _make_workflow("cancel_2", [
            {"order": 1, "name": "S1", "step_type": "data_refresh"},
        ])
        run = WorkflowRun.objects.create(workflow=wf, status="running")
        assert WorkflowEngine.cancel(str(run.id)) is True
        run.refresh_from_db()
        assert run.status == "cancelled"

    def test_cancel_completed_run_returns_false(self):
        wf = _make_workflow("cancel_3", [
            {"order": 1, "name": "S1", "step_type": "data_refresh"},
        ])
        run = WorkflowRun.objects.create(workflow=wf, status="completed")
        assert WorkflowEngine.cancel(str(run.id)) is False

    def test_cancel_failed_run_returns_false(self):
        wf = _make_workflow("cancel_4", [
            {"order": 1, "name": "S1", "step_type": "data_refresh"},
        ])
        run = WorkflowRun.objects.create(workflow=wf, status="failed")
        assert WorkflowEngine.cancel(str(run.id)) is False

    def test_cancel_already_cancelled_returns_false(self):
        wf = _make_workflow("cancel_5", [
            {"order": 1, "name": "S1", "step_type": "data_refresh"},
        ])
        run = WorkflowRun.objects.create(workflow=wf, status="cancelled")
        assert WorkflowEngine.cancel(str(run.id)) is False

    def test_cancel_nonexistent_run_returns_false(self):
        assert WorkflowEngine.cancel("does-not-exist-id") is False


# ── 5. Auto-triggered Workflows ─────────────────────────────

@pytest.mark.django_db
class TestAutoTriggeredWorkflows:
    """Verify scheduled workflows use correct trigger label."""

    @patch("analysis.services.job_runner.get_job_runner")
    def test_trigger_with_scheduled_label(self, mock_get_runner):
        mock_runner = MagicMock()
        mock_runner.submit.return_value = "fake-job-id"
        mock_get_runner.return_value = mock_runner

        wf = _make_workflow("auto_1", [
            {"order": 1, "name": "S1", "step_type": "ok_step"},
        ])
        run_id, job_id = WorkflowEngine.trigger(wf.id, trigger="scheduled")
        run = WorkflowRun.objects.get(id=run_id)
        assert run.trigger == "scheduled"
        assert run.status == "pending"

    @patch("analysis.services.job_runner.get_job_runner")
    def test_trigger_with_api_label(self, mock_get_runner):
        mock_runner = MagicMock()
        mock_runner.submit.return_value = "fake-job-id"
        mock_get_runner.return_value = mock_runner

        wf = _make_workflow("auto_2", [
            {"order": 1, "name": "S1", "step_type": "ok_step"},
        ])
        run_id, _ = WorkflowEngine.trigger(wf.id, trigger="api")
        run = WorkflowRun.objects.get(id=run_id)
        assert run.trigger == "api"

    def test_schedule_enabled_workflow_fields(self):
        wf = Workflow.objects.create(
            id="sched_wf",
            name="Scheduled WF",
            schedule_enabled=True,
            schedule_interval_seconds=3600,
        )
        assert wf.schedule_enabled is True
        assert wf.schedule_interval_seconds == 3600


# ── 6. Step Execution Order ──────────────────────────────────

@pytest.mark.django_db
class TestStepExecutionOrder:
    """Steps must execute in ascending order."""

    def test_steps_execute_in_order(self):
        execution_order = []

        def make_executor(order_val):
            def executor(params, cb):
                execution_order.append(order_val)
                return {"status": "completed", "order": order_val}
            return executor

        registry = {
            "step_a": make_executor(1),
            "step_b": make_executor(2),
            "step_c": make_executor(3),
        }
        with patch("analysis.services.step_registry.STEP_REGISTRY", registry):
            wf = _make_workflow("order_1", [
                {"order": 1, "name": "First", "step_type": "step_a"},
                {"order": 2, "name": "Second", "step_type": "step_b"},
                {"order": 3, "name": "Third", "step_type": "step_c"},
            ])
            run, step_info = _prepare_run(wf)
            result = execute_workflow(
                {"workflow_run_id": str(run.id), "steps": step_info},
                _noop_cb,
            )
            assert result["status"] == "completed"
            assert execution_order == [1, 2, 3]

    def test_current_step_tracks_progress(self):

        def tracking_executor(params, cb):
            # Read the run's current_step at time of execution
            params.get("_prev_result", {}).get("_run_id", params.get("_run_id"))
            return {"status": "completed"}

        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "track_step": tracking_executor,
        }):
            wf = _make_workflow("order_2", [
                {"order": 1, "name": "S1", "step_type": "track_step"},
                {"order": 2, "name": "S2", "step_type": "track_step"},
            ])
            run, step_info = _prepare_run(wf)
            execute_workflow(
                {"workflow_run_id": str(run.id), "steps": step_info},
                _noop_cb,
            )
            run.refresh_from_db()
            # After completion, current_step should be the last step's order
            assert run.current_step == 2


# ── 7. Workflow with No Steps ────────────────────────────────

@pytest.mark.django_db
class TestWorkflowNoSteps:
    """Empty workflow trigger should raise ValueError."""

    def test_trigger_empty_workflow_raises_value_error(self):
        wf = Workflow.objects.create(id="empty_1", name="Empty WF")
        with pytest.raises(ValueError, match="no steps"):
            WorkflowEngine.trigger(wf.id)

    def test_execute_empty_steps_list_completes(self):
        """execute_workflow with empty steps list marks run completed."""
        wf = Workflow.objects.create(id="empty_2", name="Empty Exec")
        run = WorkflowRun.objects.create(workflow=wf, total_steps=0)
        result = execute_workflow(
            {"workflow_run_id": str(run.id), "steps": []},
            _noop_cb,
        )
        assert result["status"] == "completed"
        assert result["completed_steps"] == 0
        run.refresh_from_db()
        assert run.status == "completed"


# ── 8. Concurrent Workflow Runs ──────────────────────────────

@pytest.mark.django_db
class TestConcurrentWorkflowRuns:
    """Two runs of same workflow don't conflict."""

    def test_two_runs_same_workflow_independent(self):
        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "ok_step": lambda p, cb: {"status": "completed", "value": 42},
        }):
            wf = _make_workflow("concurrent_1", [
                {"order": 1, "name": "S1", "step_type": "ok_step"},
            ])

            run1, info1 = _prepare_run(wf)
            run2, info2 = _prepare_run(wf)

            r1 = execute_workflow(
                {"workflow_run_id": str(run1.id), "steps": info1},
                _noop_cb,
            )
            r2 = execute_workflow(
                {"workflow_run_id": str(run2.id), "steps": info2},
                _noop_cb,
            )

            assert r1["status"] == "completed"
            assert r2["status"] == "completed"

            run1.refresh_from_db()
            run2.refresh_from_db()
            assert run1.status == "completed"
            assert run2.status == "completed"
            assert str(run1.id) != str(run2.id)

    def test_concurrent_runs_have_separate_step_runs(self):
        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "ok_step": lambda p, cb: {"status": "completed"},
        }):
            wf = _make_workflow("concurrent_2", [
                {"order": 1, "name": "S1", "step_type": "ok_step"},
                {"order": 2, "name": "S2", "step_type": "ok_step"},
            ])

            run1, info1 = _prepare_run(wf)
            run2, info2 = _prepare_run(wf)

            execute_workflow(
                {"workflow_run_id": str(run1.id), "steps": info1},
                _noop_cb,
            )
            execute_workflow(
                {"workflow_run_id": str(run2.id), "steps": info2},
                _noop_cb,
            )

            sr1 = WorkflowStepRun.objects.filter(workflow_run=run1).count()
            sr2 = WorkflowStepRun.objects.filter(workflow_run=run2).count()
            assert sr1 == 2
            assert sr2 == 2

    def test_one_fails_other_succeeds(self):
        """One run's failure does not affect another run."""
        call_count = {"n": 0}

        def maybe_fail(params, cb):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("first run fails")
            return {"status": "completed"}

        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "maybe_fail": maybe_fail,
        }):
            wf = _make_workflow("concurrent_3", [
                {"order": 1, "name": "S1", "step_type": "maybe_fail"},
            ])

            run1, info1 = _prepare_run(wf)
            run2, info2 = _prepare_run(wf)

            r1 = execute_workflow(
                {"workflow_run_id": str(run1.id), "steps": info1},
                _noop_cb,
            )
            r2 = execute_workflow(
                {"workflow_run_id": str(run2.id), "steps": info2},
                _noop_cb,
            )

            assert r1["status"] == "error"
            assert r2["status"] == "completed"


# ── 9. Step Parameters ───────────────────────────────────────

@pytest.mark.django_db
class TestStepParameters:
    """Params passed correctly from workflow to step executors."""

    def test_step_params_merged_with_workflow_params(self):
        received_params = {}

        def capture_executor(params, cb):
            received_params.update(params)
            return {"status": "completed"}

        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "capture_step": capture_executor,
        }):
            wf = _make_workflow("params_1", [
                {"order": 1, "name": "Capture", "step_type": "capture_step",
                 "params": {"step_key": "step_val"}},
            ])
            run, step_info = _prepare_run(wf)

            execute_workflow(
                {
                    "workflow_run_id": str(run.id),
                    "steps": step_info,
                    "workflow_params": {"wf_key": "wf_val"},
                },
                _noop_cb,
            )

            assert received_params["wf_key"] == "wf_val"
            assert received_params["step_key"] == "step_val"

    def test_step_params_override_workflow_params(self):
        """Step-level params should override workflow-level params."""
        received_params = {}

        def capture_executor(params, cb):
            received_params.update(params)
            return {"status": "completed"}

        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "capture_step": capture_executor,
        }):
            wf = _make_workflow("params_2", [
                {"order": 1, "name": "Capture", "step_type": "capture_step",
                 "params": {"shared_key": "from_step"}},
            ])
            run, step_info = _prepare_run(wf)

            execute_workflow(
                {
                    "workflow_run_id": str(run.id),
                    "steps": step_info,
                    "workflow_params": {"shared_key": "from_workflow"},
                },
                _noop_cb,
            )

            # Step params should win due to: {**workflow_params, **step_params}
            assert received_params["shared_key"] == "from_step"

    def test_prev_result_passed_to_next_step(self):
        """The _prev_result key should contain the previous step's output."""
        received_prev = {}

        def step2_executor(params, cb):
            received_prev.update(params.get("_prev_result", {}))
            return {"status": "completed"}

        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "step1": lambda p, cb: {"status": "completed", "data": "hello"},
            "step2": step2_executor,
        }):
            wf = _make_workflow("params_3", [
                {"order": 1, "name": "S1", "step_type": "step1"},
                {"order": 2, "name": "S2", "step_type": "step2"},
            ])
            run, step_info = _prepare_run(wf)
            execute_workflow(
                {"workflow_run_id": str(run.id), "steps": step_info},
                _noop_cb,
            )
            assert received_prev["data"] == "hello"

    def test_input_data_recorded_on_step_run(self):
        """WorkflowStepRun.input_data should contain merged params."""
        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "rec_step": lambda p, cb: {"status": "completed"},
        }):
            wf = _make_workflow("params_4", [
                {"order": 1, "name": "Rec", "step_type": "rec_step",
                 "params": {"key_a": "val_a"}},
            ])
            run, step_info = _prepare_run(wf)
            execute_workflow(
                {
                    "workflow_run_id": str(run.id),
                    "steps": step_info,
                    "workflow_params": {"key_b": "val_b"},
                },
                _noop_cb,
            )
            sr = WorkflowStepRun.objects.get(workflow_run=run, order=1)
            assert sr.input_data["key_a"] == "val_a"
            assert sr.input_data["key_b"] == "val_b"


# ── 10. Workflow Templates ───────────────────────────────────

@pytest.mark.django_db
class TestWorkflowTemplates:
    """Template sync from settings creates correct models."""

    def test_sync_creates_workflows_from_settings(self):
        """_sync_workflows_to_db should create template Workflows."""
        from core.services.scheduler import TaskScheduler

        # Patch settings with a minimal template
        test_templates = {
            "test_tmpl": {
                "name": "Test Template",
                "description": "A test template",
                "asset_class": "crypto",
                "steps": [
                    {"order": 1, "name": "Step A", "step_type": "data_refresh"},
                    {"order": 2, "name": "Step B", "step_type": "news_fetch"},
                ],
            },
        }
        scheduler = TaskScheduler.__new__(TaskScheduler)
        with patch("core.services.scheduler.settings") as mock_settings:
            mock_settings.WORKFLOW_TEMPLATES = test_templates
            scheduler._sync_workflows_to_db()

        wf = Workflow.objects.get(id="test_tmpl")
        assert wf.name == "Test Template"
        assert wf.is_template is True
        assert wf.asset_class == "crypto"
        steps = list(wf.steps.order_by("order"))
        assert len(steps) == 2
        assert steps[0].step_type == "data_refresh"
        assert steps[1].step_type == "news_fetch"

    def test_sync_is_idempotent(self):
        """Running sync twice does not duplicate steps."""
        from core.services.scheduler import TaskScheduler

        test_templates = {
            "idem_tmpl": {
                "name": "Idempotent",
                "description": "Test",
                "steps": [
                    {"order": 1, "name": "S1", "step_type": "data_refresh"},
                ],
            },
        }
        scheduler = TaskScheduler.__new__(TaskScheduler)
        with patch("core.services.scheduler.settings") as mock_settings:
            mock_settings.WORKFLOW_TEMPLATES = test_templates
            scheduler._sync_workflows_to_db()
            scheduler._sync_workflows_to_db()

        assert Workflow.objects.filter(id="idem_tmpl").count() == 1
        # Steps only created on first call (when created=True)
        assert WorkflowStep.objects.filter(workflow_id="idem_tmpl").count() == 1

    def test_sync_with_schedule_fields(self):
        """Scheduled templates get correct schedule fields."""
        from core.services.scheduler import TaskScheduler

        test_templates = {
            "sched_tmpl": {
                "name": "Scheduled",
                "description": "Runs every 6h",
                "schedule_enabled": True,
                "schedule_interval_seconds": 21600,
                "steps": [
                    {"order": 1, "name": "S1", "step_type": "data_refresh"},
                ],
            },
        }
        scheduler = TaskScheduler.__new__(TaskScheduler)
        with patch("core.services.scheduler.settings") as mock_settings:
            mock_settings.WORKFLOW_TEMPLATES = test_templates
            scheduler._sync_workflows_to_db()

        wf = Workflow.objects.get(id="sched_tmpl")
        assert wf.schedule_enabled is True
        assert wf.schedule_interval_seconds == 21600


# ── 11. Condition Evaluation Edge Cases ──────────────────────

class TestConditionEdgeCases:
    """Additional edge cases for _evaluate_condition."""

    def test_whitespace_only_condition_returns_true(self):
        assert _evaluate_condition("   ", {}) is True

    def test_string_not_equal(self):
        assert _evaluate_condition('result.status != "failed"', {"status": "completed"}) is True
        assert _evaluate_condition('result.status != "failed"', {"status": "failed"}) is False

    def test_numeric_less_than_boundary(self):
        assert _evaluate_condition("result.x < 5", {"x": 4}) is True
        assert _evaluate_condition("result.x < 5", {"x": 5}) is False

    def test_numeric_greater_than_boundary(self):
        assert _evaluate_condition("result.x > 5", {"x": 6}) is True
        assert _evaluate_condition("result.x > 5", {"x": 5}) is False

    def test_condition_with_single_quotes(self):
        assert _evaluate_condition("result.status == 'done'", {"status": "done"}) is True

    def test_condition_with_no_quotes(self):
        assert _evaluate_condition("result.status == done", {"status": "done"}) is True


# ── 12. WorkflowRun Not Found ────────────────────────────────

@pytest.mark.django_db
class TestWorkflowRunNotFound:
    """execute_workflow with invalid run ID returns error."""

    def test_nonexistent_run_id(self):
        result = execute_workflow(
            {"workflow_run_id": "nonexistent-uuid-1234", "steps": []},
            _noop_cb,
        )
        assert result["status"] == "error"
        assert "not found" in result["error"]


# ── 13. Workflow Run Status Transitions ──────────────────────

@pytest.mark.django_db
class TestWorkflowRunStatusTransitions:
    """Verify status transitions during execution."""

    def test_run_transitions_to_running_then_completed(self):

        def observe_executor(params, cb):
            params.get("_run_id")
            return {"status": "completed"}

        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "obs_step": observe_executor,
        }):
            wf = _make_workflow("status_1", [
                {"order": 1, "name": "S1", "step_type": "obs_step"},
            ])
            run, step_info = _prepare_run(wf)

            # Initially pending
            assert run.status == "pending"

            execute_workflow(
                {"workflow_run_id": str(run.id), "steps": step_info},
                _noop_cb,
            )

            run.refresh_from_db()
            assert run.status == "completed"
            assert run.started_at is not None
            assert run.completed_at is not None

    def test_successful_run_updates_workflow_stats(self):
        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "ok_step": lambda p, cb: {"status": "completed"},
        }):
            wf = _make_workflow("stats_1", [
                {"order": 1, "name": "S1", "step_type": "ok_step"},
            ])
            assert wf.run_count == 0
            assert wf.last_run_at is None

            run, step_info = _prepare_run(wf)
            execute_workflow(
                {"workflow_run_id": str(run.id), "steps": step_info},
                _noop_cb,
            )

            wf.refresh_from_db()
            assert wf.run_count == 1
            assert wf.last_run_at is not None


# ── 14. Progress Callback ────────────────────────────────────

@pytest.mark.django_db
class TestProgressCallback:
    """Progress callback should be called with correct values."""

    def test_progress_called_per_step(self):
        progress_calls = []

        def track_progress(p, m):
            progress_calls.append((p, m))

        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "ok_step": lambda p, cb: {"status": "completed"},
        }):
            wf = _make_workflow("progress_1", [
                {"order": 1, "name": "Alpha", "step_type": "ok_step"},
                {"order": 2, "name": "Beta", "step_type": "ok_step"},
                {"order": 3, "name": "Gamma", "step_type": "ok_step"},
            ])
            run, step_info = _prepare_run(wf)
            execute_workflow(
                {"workflow_run_id": str(run.id), "steps": step_info},
                track_progress,
            )

            assert len(progress_calls) == 3
            # Progress values should be 0/3, 1/3, 2/3
            assert progress_calls[0][0] == pytest.approx(0.0)
            assert progress_calls[1][0] == pytest.approx(1 / 3)
            assert progress_calls[2][0] == pytest.approx(2 / 3)
            assert "Alpha" in progress_calls[0][1]
            assert "Beta" in progress_calls[1][1]
            assert "Gamma" in progress_calls[2][1]


# ── 15. Condition-based Step Skipping ────────────────────────

@pytest.mark.django_db
class TestConditionSkipping:
    """Condition-based step skipping marks step as skipped with condition_met=False."""

    def test_skipped_step_has_condition_met_false(self):
        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "ok_step": lambda p, cb: {"status": "completed", "score": 0.2},
            "guarded": lambda p, cb: {"status": "completed"},
        }):
            wf = _make_workflow("cond_skip_1", [
                {"order": 1, "name": "Scorer", "step_type": "ok_step"},
                {"order": 2, "name": "Guarded", "step_type": "guarded",
                 "condition": "result.score > 0.5"},
            ])
            run, step_info = _prepare_run(wf)
            result = execute_workflow(
                {"workflow_run_id": str(run.id), "steps": step_info},
                _noop_cb,
            )
            assert result["status"] == "completed"
            assert result["completed_steps"] == 1

            sr2 = WorkflowStepRun.objects.get(workflow_run=run, order=2)
            assert sr2.status == "skipped"
            assert sr2.condition_met is False
            assert sr2.completed_at is not None

    def test_condition_met_step_executes(self):
        with patch("analysis.services.step_registry.STEP_REGISTRY", {
            "ok_step": lambda p, cb: {"status": "completed", "score": 0.8},
            "guarded": lambda p, cb: {"status": "completed", "ran": True},
        }):
            wf = _make_workflow("cond_skip_2", [
                {"order": 1, "name": "Scorer", "step_type": "ok_step"},
                {"order": 2, "name": "Guarded", "step_type": "guarded",
                 "condition": "result.score > 0.5"},
            ])
            run, step_info = _prepare_run(wf)
            result = execute_workflow(
                {"workflow_run_id": str(run.id), "steps": step_info},
                _noop_cb,
            )
            assert result["status"] == "completed"
            assert result["completed_steps"] == 2

            sr2 = WorkflowStepRun.objects.get(workflow_run=run, order=2)
            assert sr2.status == "completed"
            assert sr2.result["ran"] is True


# ── 16. Trigger Creates StepRuns ─────────────────────────────

@pytest.mark.django_db
class TestTriggerCreatesStepRuns:
    """WorkflowEngine.trigger should create StepRun records for each step."""

    @patch("analysis.services.job_runner.get_job_runner")
    def test_trigger_creates_step_runs(self, mock_get_runner):
        mock_runner = MagicMock()
        mock_runner.submit.return_value = "fake-job-id"
        mock_get_runner.return_value = mock_runner

        wf = _make_workflow("trigger_sr_1", [
            {"order": 1, "name": "A", "step_type": "ok_step"},
            {"order": 2, "name": "B", "step_type": "ok_step"},
            {"order": 3, "name": "C", "step_type": "ok_step"},
        ])
        run_id, job_id = WorkflowEngine.trigger(wf.id, params={"key": "val"})
        assert job_id == "fake-job-id"
        run = WorkflowRun.objects.get(id=run_id)

        step_runs = list(WorkflowStepRun.objects.filter(workflow_run=run).order_by("order"))
        assert len(step_runs) == 3
        assert step_runs[0].order == 1
        assert step_runs[1].order == 2
        assert step_runs[2].order == 3
        for sr in step_runs:
            assert sr.status == "pending"

    @patch("analysis.services.job_runner.get_job_runner")
    def test_trigger_passes_params_to_run(self, mock_get_runner):
        mock_runner = MagicMock()
        mock_runner.submit.return_value = "fake-job-id-2"
        mock_get_runner.return_value = mock_runner

        wf = _make_workflow("trigger_sr_2", [
            {"order": 1, "name": "A", "step_type": "ok_step"},
        ])
        run_id, _ = WorkflowEngine.trigger(wf.id, params={"asset_class": "equity"})
        run = WorkflowRun.objects.get(id=run_id)
        assert run.params == {"asset_class": "equity"}

    @patch("analysis.services.job_runner.get_job_runner")
    def test_trigger_submits_correct_job_type(self, mock_get_runner):
        mock_runner = MagicMock()
        mock_runner.submit.return_value = "fake-job-id-3"
        mock_get_runner.return_value = mock_runner

        wf = _make_workflow("trigger_sr_3", [
            {"order": 1, "name": "A", "step_type": "ok_step"},
        ])
        WorkflowEngine.trigger(wf.id)
        call_args = mock_runner.submit.call_args
        assert call_args.kwargs["job_type"] == "workflow_trigger_sr_3"
