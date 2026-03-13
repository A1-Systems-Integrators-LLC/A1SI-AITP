import uuid

from django.core.exceptions import ValidationError
from django.db import models

from market.constants import AssetClass


class BackgroundJob(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, editable=False)
    job_type = models.CharField(max_length=50, db_index=True)
    status = models.CharField(max_length=20, default="pending", db_index=True)
    progress = models.FloatField(default=0.0)
    progress_message = models.CharField(max_length=200, default="", blank=True)
    params = models.JSONField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "-created_at"],
                name="idx_job_status_created",
            ),
        ]

    VALID_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        if self.progress is not None and not (0 <= self.progress <= 1):
            errors.setdefault("progress", []).append("Progress must be between 0 and 1.")
        if self.status and self.status not in self.VALID_STATUSES:
            valid = ", ".join(sorted(self.VALID_STATUSES))
            errors.setdefault("status", []).append(
                f"Invalid status '{self.status}'. Must be one of: {valid}.",
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Job({self.id[:8]}... {self.job_type} {self.status})"


class BacktestResult(models.Model):
    job = models.ForeignKey(
        BackgroundJob,
        on_delete=models.CASCADE,
        related_name="backtest_results",
    )
    framework = models.CharField(max_length=20)
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
    )
    strategy_name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=10)
    timerange = models.CharField(max_length=50, default="", blank=True)
    metrics = models.JSONField(null=True, blank=True)
    trades = models.JSONField(null=True, blank=True)
    config = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["asset_class", "strategy_name"],
                name="idx_backtest_asset_strategy",
            ),
            models.Index(
                fields=["framework", "asset_class"],
                name="idx_backtest_framework_asset",
            ),
            models.Index(
                fields=["symbol", "timeframe"],
                name="idx_backtest_symbol_tf",
            ),
        ]

    def __str__(self):
        return f"Backtest({self.strategy_name} {self.symbol} {self.timeframe})"


# ── Workflow models ──────────────────────────────────────────


class Workflow(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField(default="", blank=True)
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
    )
    is_template = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    schedule_interval_seconds = models.IntegerField(null=True, blank=True)
    schedule_enabled = models.BooleanField(default=False)
    params = models.JSONField(default=dict, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    run_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        if self.schedule_interval_seconds is not None and self.schedule_interval_seconds <= 0:
            errors.setdefault("schedule_interval_seconds", []).append(
                "Schedule interval must be > 0 when set.",
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Workflow({self.id}: {self.name})"


class WorkflowStep(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="steps")
    order = models.IntegerField()
    name = models.CharField(max_length=100)
    step_type = models.CharField(max_length=50)
    params = models.JSONField(default=dict, blank=True)
    condition = models.CharField(max_length=200, default="", blank=True)
    timeout_seconds = models.IntegerField(default=300)

    class Meta:
        ordering = ["order"]
        unique_together = [("workflow", "order")]

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        if self.order is not None and self.order < 1:
            errors.setdefault("order", []).append("Order must be >= 1.")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            errors.setdefault("timeout_seconds", []).append("Timeout must be > 0.")
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Step({self.workflow_id}/{self.order}: {self.name})"


class WorkflowRun(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]
    TRIGGER_CHOICES = [
        ("manual", "Manual"),
        ("scheduled", "Scheduled"),
        ("api", "API"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="runs")
    job = models.OneToOneField(
        BackgroundJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_run",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    trigger = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default="manual")
    params = models.JSONField(default=dict, blank=True)
    current_step = models.IntegerField(default=0)
    total_steps = models.IntegerField(default=0)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["workflow", "-created_at"],
                name="idx_wfrun_workflow_created",
            ),
        ]

    def __str__(self):
        return f"WorkflowRun({self.id[:8]}... {self.workflow_id} {self.status})"


class WorkflowStepRun(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    workflow_run = models.ForeignKey(
        WorkflowRun,
        on_delete=models.CASCADE,
        related_name="step_runs",
    )
    step = models.ForeignKey(WorkflowStep, on_delete=models.CASCADE, related_name="runs")
    order = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    input_data = models.JSONField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    condition_met = models.BooleanField(default=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"StepRun({str(self.workflow_run_id)[:8]}... step {self.order} {self.status})"


# ── ML tracking models ──────────────────────────────────────


class MLPrediction(models.Model):
    """Tracks individual ML predictions for outcome analysis."""

    DIRECTION_CHOICES = [("up", "Up"), ("down", "Down")]

    prediction_id = models.CharField(
        max_length=36,
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    model_id = models.CharField(max_length=100, db_index=True)
    symbol = models.CharField(max_length=20)
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
    )
    probability = models.FloatField(help_text="Calibrated probability 0.0-1.0")
    confidence = models.FloatField(default=0.0)
    direction = models.CharField(max_length=4, choices=DIRECTION_CHOICES)
    regime = models.CharField(max_length=30, default="", blank=True)
    actual_direction = models.CharField(
        max_length=4,
        choices=DIRECTION_CHOICES,
        null=True,
        blank=True,
    )
    correct = models.BooleanField(null=True, blank=True)
    predicted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-predicted_at"]
        indexes = [
            models.Index(fields=["model_id", "-predicted_at"], name="idx_mlpred_model_date"),
            models.Index(fields=["symbol", "-predicted_at"], name="idx_mlpred_symbol_date"),
        ]

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        if self.probability is not None and not (0 <= self.probability <= 1):
            errors.setdefault("probability", []).append("Probability must be between 0 and 1.")
        if self.confidence is not None and not (0 <= self.confidence <= 1):
            errors.setdefault("confidence", []).append("Confidence must be between 0 and 1.")
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"MLPrediction({self.symbol} {self.direction} p={self.probability:.2f})"


class MLModelPerformance(models.Model):
    """Tracks aggregate model accuracy and retraining needs."""

    model_id = models.CharField(max_length=100, primary_key=True)
    total_predictions = models.IntegerField(default=0)
    correct_predictions = models.IntegerField(default=0)
    rolling_accuracy = models.FloatField(default=0.0, help_text="Rolling accuracy 0.0-1.0")
    accuracy_by_regime = models.JSONField(default=dict, blank=True)
    retrain_recommended = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        if self.rolling_accuracy is not None and not (0 <= self.rolling_accuracy <= 1):
            errors.setdefault("rolling_accuracy", []).append(
                "Rolling accuracy must be between 0 and 1.",
            )
        if self.total_predictions is not None and self.total_predictions < 0:
            errors.setdefault("total_predictions", []).append(
                "Total predictions must be >= 0.",
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"MLModelPerf({self.model_id} acc={self.rolling_accuracy:.2f})"


# ── Signal attribution models ──────────────────────────────────────


class SignalAttribution(models.Model):
    """Links signal components to trade outcomes for feedback & adaptive tuning."""

    OUTCOME_CHOICES = [("win", "Win"), ("loss", "Loss"), ("open", "Open")]

    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.CharField(max_length=36, db_index=True)
    symbol = models.CharField(max_length=20)
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
    )
    strategy = models.CharField(max_length=100)
    composite_score = models.FloatField()
    ml_contribution = models.FloatField(default=0.0)
    sentiment_contribution = models.FloatField(default=0.0)
    regime_contribution = models.FloatField(default=0.0)
    scanner_contribution = models.FloatField(default=0.0)
    screen_contribution = models.FloatField(default=0.0)
    win_rate_contribution = models.FloatField(default=0.0)
    position_modifier = models.FloatField(default=1.0)
    entry_regime = models.CharField(max_length=30, default="", blank=True)
    outcome = models.CharField(max_length=4, choices=OUTCOME_CHOICES, default="open")
    pnl = models.FloatField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(
                fields=["symbol", "-recorded_at"],
                name="idx_sigattr_symbol_date",
            ),
            models.Index(
                fields=["strategy", "asset_class", "-recorded_at"],
                name="idx_sigattr_strat_asset",
            ),
            models.Index(
                fields=["outcome", "-recorded_at"],
                name="idx_sigattr_outcome_date",
            ),
        ]

    VALID_OUTCOMES = {"win", "loss", "open"}

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        if self.composite_score is not None and not (0 <= self.composite_score <= 100):
            errors.setdefault("composite_score", []).append(
                "Composite score must be between 0 and 100.",
            )
        if self.outcome and self.outcome not in self.VALID_OUTCOMES:
            valid = ", ".join(sorted(self.VALID_OUTCOMES))
            errors.setdefault("outcome", []).append(
                f"Invalid outcome '{self.outcome}'. Must be one of: {valid}.",
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"SignalAttr({self.symbol} {self.strategy}"
            f" {self.outcome} score={self.composite_score:.1f})"
        )


class ScreenResult(models.Model):
    job = models.ForeignKey(BackgroundJob, on_delete=models.CASCADE, related_name="screen_results")
    symbol = models.CharField(max_length=20)
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
    )
    timeframe = models.CharField(max_length=10)
    strategy_name = models.CharField(max_length=50)
    top_results = models.JSONField(null=True, blank=True)
    summary = models.JSONField(null=True, blank=True)
    total_combinations = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["asset_class", "-created_at"],
                name="idx_screen_asset_created",
            ),
        ]

    def __str__(self):
        return f"Screen({self.strategy_name} {self.symbol} {self.timeframe})"
