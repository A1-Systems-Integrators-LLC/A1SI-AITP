import uuid

from django.db import models


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

    def __str__(self):
        return f"Job({self.id[:8]}... {self.job_type} {self.status})"


class BacktestResult(models.Model):
    job = models.ForeignKey(
        BackgroundJob, on_delete=models.CASCADE,
        related_name="backtest_results",
    )
    framework = models.CharField(max_length=20)
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


class ScreenResult(models.Model):
    job = models.ForeignKey(BackgroundJob, on_delete=models.CASCADE, related_name="screen_results")
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=10)
    strategy_name = models.CharField(max_length=50)
    top_results = models.JSONField(null=True, blank=True)
    summary = models.JSONField(null=True, blank=True)
    total_combinations = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
