from rest_framework import serializers

from core.models import AuditLog, NotificationPreferences, ScheduledTask


class ScheduledTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduledTask
        fields = [
            "id",
            "name",
            "description",
            "task_type",
            "status",
            "interval_seconds",
            "params",
            "last_run_at",
            "last_run_status",
            "last_run_job_id",
            "next_run_at",
            "run_count",
            "error_count",
            "created_at",
            "updated_at",
        ]


class SchedulerStatusSerializer(serializers.Serializer):
    running = serializers.BooleanField()
    total_tasks = serializers.IntegerField()
    active_tasks = serializers.IntegerField()
    paused_tasks = serializers.IntegerField()


class TaskTriggerResponseSerializer(serializers.Serializer):
    job_id = serializers.CharField()
    task_id = serializers.CharField()
    message = serializers.CharField()


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = "__all__"


class DashboardPortfolioKPISerializer(serializers.Serializer):
    count = serializers.IntegerField()
    total_value = serializers.FloatField()
    total_cost = serializers.FloatField()
    unrealized_pnl = serializers.FloatField()
    pnl_pct = serializers.FloatField()


class DashboardTradingKPISerializer(serializers.Serializer):
    total_trades = serializers.IntegerField()
    win_rate = serializers.FloatField()
    total_pnl = serializers.FloatField()
    profit_factor = serializers.FloatField(allow_null=True)
    open_orders = serializers.IntegerField()


class DashboardRiskKPISerializer(serializers.Serializer):
    equity = serializers.FloatField()
    drawdown = serializers.FloatField()
    daily_pnl = serializers.FloatField()
    is_halted = serializers.BooleanField()
    open_positions = serializers.IntegerField()


class DashboardPlatformKPISerializer(serializers.Serializer):
    data_files = serializers.IntegerField()
    active_jobs = serializers.IntegerField()
    framework_count = serializers.IntegerField()


class DashboardKPISerializer(serializers.Serializer):
    portfolio = DashboardPortfolioKPISerializer()
    trading = DashboardTradingKPISerializer()
    risk = DashboardRiskKPISerializer()
    platform = DashboardPlatformKPISerializer()
    generated_at = serializers.CharField()


# ── OpenAPI response serializers ─────────────────────────────


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()


class DetailedHealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    checks = serializers.DictField()


class PlatformStatusSerializer(serializers.Serializer):
    frameworks = serializers.ListField()
    data_files = serializers.IntegerField()
    active_jobs = serializers.IntegerField()


class AuditLogListResponseSerializer(serializers.Serializer):
    results = AuditLogSerializer(many=True)
    total = serializers.IntegerField()


class TaskActionResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class NotificationPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreferences
        fields = [
            "portfolio_id",
            "telegram_enabled",
            "webhook_enabled",
            "on_order_submitted",
            "on_order_filled",
            "on_order_cancelled",
            "on_risk_halt",
            "on_trade_rejected",
            "on_daily_summary",
        ]
        read_only_fields = ["portfolio_id"]
