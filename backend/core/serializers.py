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
