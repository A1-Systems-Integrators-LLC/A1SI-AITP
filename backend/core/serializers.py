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
    equity_source = serializers.CharField(required=False, allow_null=True)


class DashboardTradingKPISerializer(serializers.Serializer):
    total_trades = serializers.IntegerField()
    win_rate = serializers.FloatField()
    total_pnl = serializers.FloatField()
    profit_factor = serializers.FloatField(allow_null=True)
    open_orders = serializers.IntegerField()
    total_orders = serializers.IntegerField(required=False, default=0)
    rejected_orders = serializers.IntegerField(required=False, default=0)
    filled_orders = serializers.IntegerField(required=False, default=0)
    rejection_rate = serializers.FloatField(required=False, default=0.0)


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


class DashboardPaperTradingInstanceSerializer(serializers.Serializer):
    name = serializers.CharField()
    running = serializers.BooleanField()
    strategy = serializers.CharField(allow_null=True)
    pnl = serializers.FloatField()
    open_trades = serializers.IntegerField()
    closed_trades = serializers.IntegerField()


class DashboardPaperTradingKPISerializer(serializers.Serializer):
    instances_running = serializers.IntegerField()
    total_pnl = serializers.FloatField()
    total_pnl_pct = serializers.FloatField()
    open_trades = serializers.IntegerField()
    closed_trades = serializers.IntegerField()
    win_rate = serializers.FloatField()
    instances = DashboardPaperTradingInstanceSerializer(many=True)


class FreqtradeInstanceHealthSerializer(serializers.Serializer):
    name = serializers.CharField()
    port = serializers.IntegerField()
    running = serializers.BooleanField()
    enabled = serializers.BooleanField()


class SystemHealthSerializer(serializers.Serializer):
    scheduler_running = serializers.BooleanField()
    last_data_refresh = serializers.CharField(allow_null=True)
    freqtrade_instances = FreqtradeInstanceHealthSerializer(many=True)
    active_tasks = serializers.IntegerField()
    total_jobs_completed = serializers.IntegerField()
    total_jobs_failed = serializers.IntegerField()


class ActivityFeedItemSerializer(serializers.Serializer):
    type = serializers.CharField()
    message = serializers.CharField()
    timestamp = serializers.CharField()
    status = serializers.CharField(required=False, allow_null=True)


class OrchestratorStateSerializer(serializers.Serializer):
    strategy = serializers.CharField()
    action = serializers.CharField()
    alignment = serializers.FloatField()
    regime = serializers.CharField()


class LearningStatusSerializer(serializers.Serializer):
    ml_accuracy = serializers.FloatField(allow_null=True)
    ml_predictions_total = serializers.IntegerField()
    ml_models_count = serializers.IntegerField()
    ml_last_trained = serializers.CharField(allow_null=True)
    signal_attributions = serializers.IntegerField()
    orchestrator_states = OrchestratorStateSerializer(many=True)


class DashboardKPISerializer(serializers.Serializer):
    portfolio = DashboardPortfolioKPISerializer()
    trading = DashboardTradingKPISerializer()
    risk = DashboardRiskKPISerializer()
    platform = DashboardPlatformKPISerializer()
    paper_trading = DashboardPaperTradingKPISerializer()
    system_health = SystemHealthSerializer()
    activity_feed = ActivityFeedItemSerializer(many=True)
    learning_status = LearningStatusSerializer()
    generated_at = serializers.CharField()


# ── OpenAPI response serializers ─────────────────────────────


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()


class DetailedHealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    checks = serializers.DictField()


class FrameworkStatusSerializer(serializers.Serializer):
    name = serializers.CharField()
    installed = serializers.BooleanField()
    version = serializers.CharField(allow_null=True)
    status = serializers.ChoiceField(choices=["running", "idle", "not_installed"])
    status_label = serializers.CharField()
    details = serializers.DictField(allow_null=True)


class PlatformStatusSerializer(serializers.Serializer):
    frameworks = FrameworkStatusSerializer(many=True)
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
