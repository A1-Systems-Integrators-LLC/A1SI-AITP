from rest_framework import serializers

from analysis.models import (
    BackgroundJob,
    BacktestResult,
    ScreenResult,
    Workflow,
    WorkflowRun,
    WorkflowStep,
    WorkflowStepRun,
)
from market.constants import AssetClass


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackgroundJob
        fields = [
            "id",
            "job_type",
            "status",
            "progress",
            "progress_message",
            "params",
            "result",
            "error",
            "started_at",
            "completed_at",
            "created_at",
        ]


class BacktestRequestSerializer(serializers.Serializer):
    framework = serializers.CharField(default="freqtrade")
    strategy = serializers.CharField(default="SampleStrategy", min_length=1)
    symbol = serializers.RegexField(
        regex=r"^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$",
        max_length=20,
        default="BTC/USDT",
        help_text="Trading pair, e.g. BTC/USDT",
    )
    timeframe = serializers.RegexField(
        regex=r"^[0-9]+[smhdwM]$",
        max_length=10,
        default="1h",
        help_text="Timeframe, e.g. 1h, 4h, 1d",
    )
    timerange = serializers.CharField(default="", allow_blank=True)
    exchange = serializers.CharField(default="kraken", min_length=1)
    asset_class = serializers.ChoiceField(
        choices=AssetClass.choices, default=AssetClass.CRYPTO,
    )


class StrategyInfoSerializer(serializers.Serializer):
    name = serializers.CharField()
    framework = serializers.CharField()
    file_path = serializers.CharField()


class BacktestResultSerializer(serializers.ModelSerializer):
    job_id = serializers.CharField(source="job.id", read_only=True)

    class Meta:
        model = BacktestResult
        fields = [
            "id",
            "job_id",
            "framework",
            "asset_class",
            "strategy_name",
            "symbol",
            "timeframe",
            "timerange",
            "metrics",
            "trades",
            "config",
            "created_at",
        ]


class ScreenRequestSerializer(serializers.Serializer):
    symbol = serializers.RegexField(
        regex=r"^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$",
        max_length=20,
        default="BTC/USDT",
        help_text="Trading pair, e.g. BTC/USDT",
    )
    timeframe = serializers.RegexField(
        regex=r"^[0-9]+[smhdwM]$",
        max_length=10,
        default="1h",
        help_text="Timeframe, e.g. 1h, 4h, 1d",
    )
    exchange = serializers.CharField(default="kraken", min_length=1)
    fees = serializers.FloatField(default=0.001, min_value=0.0, max_value=0.1)
    asset_class = serializers.ChoiceField(
        choices=AssetClass.choices, default=AssetClass.CRYPTO,
    )


class ScreenResultSerializer(serializers.ModelSerializer):
    job_id = serializers.CharField(source="job.id", read_only=True)

    class Meta:
        model = ScreenResult
        fields = [
            "id",
            "job_id",
            "symbol",
            "asset_class",
            "timeframe",
            "strategy_name",
            "top_results",
            "summary",
            "total_combinations",
            "created_at",
        ]


class DataFileInfoSerializer(serializers.Serializer):
    exchange = serializers.CharField()
    symbol = serializers.CharField()
    timeframe = serializers.CharField()
    rows = serializers.IntegerField()
    start = serializers.CharField(allow_null=True)
    end = serializers.CharField(allow_null=True)
    file = serializers.CharField()


class DataDetailInfoSerializer(serializers.Serializer):
    exchange = serializers.CharField()
    symbol = serializers.CharField()
    timeframe = serializers.CharField()
    rows = serializers.IntegerField()
    start = serializers.CharField(allow_null=True)
    end = serializers.CharField(allow_null=True)
    columns = serializers.ListField(child=serializers.CharField())
    file_size_mb = serializers.FloatField()


class DataDownloadRequestSerializer(serializers.Serializer):
    symbols = serializers.ListField(child=serializers.CharField(), default=["BTC/USDT", "ETH/USDT"])
    timeframes = serializers.ListField(child=serializers.CharField(), default=["1h"])
    exchange = serializers.CharField(default="kraken", min_length=1)
    since_days = serializers.IntegerField(default=365, min_value=1, max_value=3650)
    asset_class = serializers.ChoiceField(
        choices=AssetClass.choices, default=AssetClass.CRYPTO,
    )


class DataGenerateSampleRequestSerializer(serializers.Serializer):
    symbols = serializers.ListField(child=serializers.CharField(), default=["BTC/USDT", "ETH/USDT"])
    timeframes = serializers.ListField(child=serializers.CharField(), default=["1h"])
    days = serializers.IntegerField(default=90, min_value=1, max_value=3650)


class PaperTradingStartSerializer(serializers.Serializer):
    strategy = serializers.CharField(default="CryptoInvestorV1")


class PaperTradingStatusSerializer(serializers.Serializer):
    running = serializers.BooleanField()
    strategy = serializers.CharField(allow_null=True, required=False)
    pid = serializers.IntegerField(allow_null=True, required=False)
    started_at = serializers.CharField(allow_null=True, required=False)
    uptime_seconds = serializers.IntegerField(default=0)
    exit_code = serializers.IntegerField(allow_null=True, required=False)


class PaperTradingActionSerializer(serializers.Serializer):
    status = serializers.CharField()
    strategy = serializers.CharField(allow_null=True, required=False)
    pid = serializers.IntegerField(allow_null=True, required=False)
    started_at = serializers.CharField(allow_null=True, required=False)
    error = serializers.CharField(allow_null=True, required=False)


class MLTrainRequestSerializer(serializers.Serializer):
    symbol = serializers.CharField(default="BTC/USDT")
    timeframe = serializers.CharField(default="1h")
    exchange = serializers.CharField(default="kraken")
    test_ratio = serializers.FloatField(default=0.2, min_value=0.05, max_value=0.5)


class MLPredictRequestSerializer(serializers.Serializer):
    model_id = serializers.CharField()
    symbol = serializers.CharField(default="BTC/USDT")
    timeframe = serializers.CharField(default="1h")
    exchange = serializers.CharField(default="kraken")
    bars = serializers.IntegerField(default=50, min_value=1, max_value=1000)


class JobAcceptedSerializer(serializers.Serializer):
    job_id = serializers.CharField()
    status = serializers.CharField()


class DataQualityReportSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    timeframe = serializers.CharField()
    exchange = serializers.CharField()
    rows = serializers.IntegerField()
    date_range = serializers.ListField(child=serializers.CharField(allow_null=True))
    gaps = serializers.ListField(child=serializers.DictField())
    nan_columns = serializers.DictField(child=serializers.IntegerField())
    outliers = serializers.ListField(child=serializers.DictField())
    ohlc_violations = serializers.ListField(child=serializers.DictField())
    is_stale = serializers.BooleanField()
    stale_hours = serializers.FloatField()
    passed = serializers.BooleanField()
    issues_summary = serializers.ListField(child=serializers.CharField())


class DataQualitySummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    passed = serializers.IntegerField()
    failed = serializers.IntegerField()
    reports = DataQualityReportSerializer(many=True)


class BacktestComparisonMetricSerializer(serializers.Serializer):
    metric = serializers.CharField()
    values = serializers.DictField(child=serializers.FloatField(allow_null=True))
    best = serializers.CharField(allow_null=True)
    rankings = serializers.DictField(child=serializers.IntegerField())


class BacktestComparisonSerializer(serializers.Serializer):
    results = BacktestResultSerializer(many=True)
    comparison = serializers.DictField()


# ── Workflow serializers ─────────────────────────────────────


class WorkflowStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowStep
        fields = ["id", "order", "name", "step_type", "params", "condition", "timeout_seconds"]


class WorkflowListSerializer(serializers.ModelSerializer):
    step_count = serializers.IntegerField(source="steps.count", read_only=True)

    class Meta:
        model = Workflow
        fields = [
            "id", "name", "description", "asset_class",
            "is_template", "is_active",
            "schedule_interval_seconds", "schedule_enabled",
            "last_run_at", "run_count", "step_count",
            "created_at", "updated_at",
        ]


class WorkflowDetailSerializer(serializers.ModelSerializer):
    steps = WorkflowStepSerializer(many=True, read_only=True)

    class Meta:
        model = Workflow
        fields = [
            "id", "name", "description", "asset_class",
            "is_template", "is_active",
            "schedule_interval_seconds", "schedule_enabled",
            "params", "last_run_at", "run_count", "steps",
            "created_at", "updated_at",
        ]


class WorkflowCreateStepSerializer(serializers.Serializer):
    order = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=100)
    step_type = serializers.CharField(max_length=50)
    params = serializers.DictField(default=dict)
    condition = serializers.CharField(default="", allow_blank=True, max_length=200)
    timeout_seconds = serializers.IntegerField(default=300, min_value=1, max_value=3600)


class WorkflowCreateSerializer(serializers.Serializer):
    id = serializers.RegexField(
        regex=r"^[a-z0-9_]+$",
        max_length=50,
        help_text="Workflow ID (lowercase alphanumeric + underscore)",
    )
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(default="", allow_blank=True)
    asset_class = serializers.ChoiceField(choices=AssetClass.choices, default=AssetClass.CRYPTO)
    params = serializers.DictField(default=dict)
    schedule_interval_seconds = serializers.IntegerField(
        required=False, allow_null=True, min_value=60,
    )
    schedule_enabled = serializers.BooleanField(default=False)
    steps = WorkflowCreateStepSerializer(many=True)


# ── OpenAPI response serializers ─────────────────────────────


class JobCancelResponseSerializer(serializers.Serializer):
    status = serializers.CharField()


class MLModelInfoSerializer(serializers.Serializer):
    model_id = serializers.CharField()
    symbol = serializers.CharField()
    timeframe = serializers.CharField()
    exchange = serializers.CharField()
    created_at = serializers.CharField()


class MLPredictionResponseSerializer(serializers.Serializer):
    model_id = serializers.CharField()
    prediction = serializers.IntegerField()
    confidence = serializers.FloatField()


class WorkflowTriggerResponseSerializer(serializers.Serializer):
    workflow_run_id = serializers.CharField()
    job_id = serializers.CharField()


class WorkflowScheduleResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    workflow_id = serializers.CharField()


class WorkflowStepRunSerializer(serializers.ModelSerializer):
    step_name = serializers.CharField(source="step.name", read_only=True)
    step_type = serializers.CharField(source="step.step_type", read_only=True)

    class Meta:
        model = WorkflowStepRun
        fields = [
            "id", "order", "step_name", "step_type", "status",
            "input_data", "result", "error", "condition_met",
            "started_at", "completed_at", "duration_seconds",
        ]


class WorkflowRunListSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="workflow.name", read_only=True)
    job_id = serializers.CharField(source="job.id", read_only=True, default=None)

    class Meta:
        model = WorkflowRun
        fields = [
            "id", "workflow_name", "status", "trigger",
            "current_step", "total_steps", "job_id",
            "started_at", "completed_at", "created_at",
        ]


class WorkflowRunDetailSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="workflow.name", read_only=True)
    job_id = serializers.CharField(source="job.id", read_only=True, default=None)
    step_runs = WorkflowStepRunSerializer(many=True, read_only=True)

    class Meta:
        model = WorkflowRun
        fields = [
            "id", "workflow_name", "status", "trigger", "params",
            "current_step", "total_steps", "result", "error",
            "job_id", "step_runs",
            "started_at", "completed_at", "created_at",
        ]
