from django.db import models


class ScheduledTask(models.Model):
    ACTIVE = "active"
    PAUSED = "paused"
    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (PAUSED, "Paused"),
    ]

    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=500, default="", blank=True)
    task_type = models.CharField(max_length=50, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    interval_seconds = models.IntegerField(null=True, blank=True)
    params = models.JSONField(default=dict, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(max_length=20, default="", blank=True)
    last_run_job_id = models.CharField(max_length=36, default="", blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    run_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.task_type}) [{self.status}]"


class AuditLog(models.Model):
    user = models.CharField(max_length=150)
    action = models.CharField(max_length=500)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    status_code = models.IntegerField(default=200)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at} {self.user} {self.action}"


class NotificationPreferences(models.Model):
    portfolio_id = models.IntegerField(unique=True)
    telegram_enabled = models.BooleanField(default=True)
    webhook_enabled = models.BooleanField(default=False)
    # Per-event toggles
    on_order_submitted = models.BooleanField(default=True)
    on_order_filled = models.BooleanField(default=True)
    on_order_cancelled = models.BooleanField(default=True)
    on_risk_halt = models.BooleanField(default=True)
    on_trade_rejected = models.BooleanField(default=True)
    on_daily_summary = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "notification preferences"

    def __str__(self):
        return f"NotificationPreferences(portfolio={self.portfolio_id})"
