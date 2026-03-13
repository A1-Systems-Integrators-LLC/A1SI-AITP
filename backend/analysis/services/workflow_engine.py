"""Workflow engine — triggers and executes multi-step workflow pipelines.

Walks steps sequentially, evaluates conditions, passes outputs forward.
Uses JobRunner for background execution with BackgroundJob tracking.
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("workflow")

# Safe condition pattern: result.field op value
_CONDITION_RE = re.compile(
    r'^result\.(\w+)\s*(==|!=|>|<|>=|<=)\s*["\']?([^"\']*)["\']?$',
)


def _evaluate_condition(condition: str, prev_result: dict) -> bool:
    """Safely evaluate a step condition against the previous result.

    Supports patterns like:
        result.status == "completed"
        result.score > 0.5
        result.alerts_triggered > 0

    Returns True if condition is empty or evaluates to true.
    """
    if not condition or not condition.strip():
        return True

    match = _CONDITION_RE.match(condition.strip())
    if not match:
        logger.warning("Invalid condition syntax: %s", condition)
        return True  # Proceed on unparseable conditions

    field, op, value = match.groups()
    actual = prev_result.get(field)
    if actual is None:
        return False

    # Try numeric comparison
    try:
        actual_num = float(actual)
        value_num = float(value)
        if op == "==":
            return actual_num == value_num
        if op == "!=":
            return actual_num != value_num
        if op == ">":
            return actual_num > value_num
        if op == "<":
            return actual_num < value_num
        if op == ">=":
            return actual_num >= value_num
        if op == "<=":
            return actual_num <= value_num
    except (ValueError, TypeError):
        pass

    # String comparison
    actual_str = str(actual)
    if op == "==":
        return actual_str == value
    if op == "!=":
        return actual_str != value

    return True


def execute_workflow(params: dict, progress_cb: Any) -> dict[str, Any]:
    """Execute a workflow run — called by JobRunner in a background thread.

    Params should include:
        - workflow_run_id: str
        - steps: list[dict] with step_id, order, name, step_type, etc.
        - workflow_params: dict (global workflow params)
    """
    from core.services.metrics import timed

    with timed("workflow_execution_seconds"):
        from analysis.models import WorkflowRun, WorkflowStepRun
        from analysis.services.step_registry import STEP_REGISTRY

        run_id = params["workflow_run_id"]
        steps = params["steps"]
        workflow_params = params.get("workflow_params", {})

        try:
            run = WorkflowRun.objects.get(id=run_id)
        except WorkflowRun.DoesNotExist:
            return {"status": "error", "error": f"WorkflowRun {run_id} not found"}

        run.status = "running"
        run.started_at = datetime.now(tz=timezone.utc)
        run.total_steps = len(steps)
        run.save(update_fields=["status", "started_at", "total_steps"])

        prev_result: dict[str, Any] = {}
        completed_steps = 0

        for i, step_info in enumerate(steps):
            step_order = step_info["order"]
            step_type = step_info["step_type"]
            step_params = {**workflow_params, **step_info.get("params", {})}
            condition = step_info.get("condition", "")

            run.current_step = step_order
            run.save(update_fields=["current_step"])

            progress_cb(i / len(steps), f"Running step {step_order}: {step_info['name']}")

            # Get step run record
            try:
                step_run = WorkflowStepRun.objects.get(
                    workflow_run=run,
                    order=step_order,
                )
            except WorkflowStepRun.DoesNotExist:
                logger.error("StepRun not found for run=%s order=%d", run_id, step_order)
                continue

            # Evaluate condition
            if condition and not _evaluate_condition(condition, prev_result):
                step_run.status = "skipped"
                step_run.condition_met = False
                step_run.completed_at = datetime.now(tz=timezone.utc)
                step_run.save()
                logger.info("Step %d skipped: condition not met (%s)", step_order, condition)
                continue

            # Find executor
            executor = STEP_REGISTRY.get(step_type)
            if not executor:
                step_run.status = "failed"
                step_run.error = f"Unknown step type: {step_type}"
                step_run.completed_at = datetime.now(tz=timezone.utc)
                step_run.save()
                run.status = "failed"
                run.error = f"Unknown step type: {step_type}"
                run.completed_at = datetime.now(tz=timezone.utc)
                run.save()
                return {"status": "error", "error": f"Unknown step type: {step_type}"}

            # Execute step
            step_run.status = "running"
            step_run.started_at = datetime.now(tz=timezone.utc)
            step_run.input_data = {"_prev_result": prev_result, **step_params}
            step_run.save()

            start_time = time.monotonic()
            try:
                # Pass previous result in params
                exec_params = {**step_params, "_prev_result": prev_result}
                step_result = executor(exec_params, lambda p, m: None)

                duration = time.monotonic() - start_time
                step_run.status = "completed"
                step_run.result = step_result
                step_run.duration_seconds = round(duration, 3)
                step_run.completed_at = datetime.now(tz=timezone.utc)
                step_run.save()

                prev_result = step_result
                completed_steps += 1

            except Exception as e:
                duration = time.monotonic() - start_time
                step_run.status = "failed"
                step_run.error = str(e)
                step_run.duration_seconds = round(duration, 3)
                step_run.completed_at = datetime.now(tz=timezone.utc)
                step_run.save()

                run.status = "failed"
                run.error = f"Step {step_order} ({step_info['name']}) failed: {e}"
                run.completed_at = datetime.now(tz=timezone.utc)
                run.save()
                return {"status": "error", "error": str(e), "failed_step": step_order}

        # All steps completed
        run.status = "completed"
        run.result = prev_result
        run.completed_at = datetime.now(tz=timezone.utc)
        run.save()

        # Update workflow stats
        from analysis.models import Workflow

        Workflow.objects.filter(id=run.workflow_id).update(
            last_run_at=datetime.now(tz=timezone.utc),
            run_count=run.workflow.run_count + 1,
        )

        return {
            "status": "completed",
            "completed_steps": completed_steps,
            "total_steps": len(steps),
            "result": prev_result,
        }


class WorkflowEngine:
    """Triggers workflow execution via JobRunner."""

    @staticmethod
    def trigger(
        workflow_id: str,
        trigger: str = "manual",
        params: dict | None = None,
    ) -> tuple[str, str]:
        """Create a WorkflowRun and submit to JobRunner.

        Returns (workflow_run_id, job_id).
        """
        from analysis.models import Workflow, WorkflowRun, WorkflowStepRun
        from analysis.services.job_runner import get_job_runner

        workflow = Workflow.objects.get(id=workflow_id)
        steps = list(workflow.steps.order_by("order"))

        if not steps:
            raise ValueError(f"Workflow {workflow_id} has no steps")

        # Create run + step runs
        run = WorkflowRun.objects.create(
            workflow=workflow,
            trigger=trigger,
            params=params or {},
            total_steps=len(steps),
        )

        step_info_list = []
        for step in steps:
            WorkflowStepRun.objects.create(
                workflow_run=run,
                step=step,
                order=step.order,
            )
            step_info_list.append({
                "step_id": step.id,
                "order": step.order,
                "name": step.name,
                "step_type": step.step_type,
                "params": step.params,
                "condition": step.condition,
                "timeout_seconds": step.timeout_seconds,
            })

        # Submit to JobRunner
        job_id = get_job_runner().submit(
            job_type=f"workflow_{workflow_id}",
            run_fn=execute_workflow,
            params={
                "workflow_run_id": str(run.id),
                "steps": step_info_list,
                "workflow_params": {**(params or {}), **workflow.params},
            },
        )

        # Link job to run
        from analysis.models import BackgroundJob

        try:
            job = BackgroundJob.objects.get(id=job_id)
            run.job = job
            run.save(update_fields=["job"])
        except BackgroundJob.DoesNotExist:
            pass

        return str(run.id), job_id

    @staticmethod
    def cancel(run_id: str) -> bool:
        """Cancel a running workflow."""
        from analysis.models import WorkflowRun

        try:
            run = WorkflowRun.objects.get(id=run_id)
        except WorkflowRun.DoesNotExist:
            return False

        if run.status not in ("pending", "running"):
            return False

        run.status = "cancelled"
        run.completed_at = datetime.now(tz=timezone.utc)
        run.save(update_fields=["status", "completed_at"])

        # Cancel the background job too
        if run.job_id:
            from analysis.services.job_runner import get_job_runner

            get_job_runner().cancel_job(run.job_id)

        return True
