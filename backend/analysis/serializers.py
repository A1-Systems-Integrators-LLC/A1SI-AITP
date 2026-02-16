from rest_framework import serializers

from analysis.models import BackgroundJob, BacktestResult, ScreenResult


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackgroundJob
        fields = [
            "id", "job_type", "status", "progress", "progress_message",
            "params", "result", "error", "started_at", "completed_at", "created_at",
        ]


class BacktestRequestSerializer(serializers.Serializer):
    framework = serializers.CharField(default="freqtrade")
    strategy = serializers.CharField(default="SampleStrategy")
    symbol = serializers.CharField(default="BTC/USDT")
    timeframe = serializers.CharField(default="1h")
    timerange = serializers.CharField(default="", allow_blank=True)
    exchange = serializers.CharField(default="binance")


class StrategyInfoSerializer(serializers.Serializer):
    name = serializers.CharField()
    framework = serializers.CharField()
    file_path = serializers.CharField()


class BacktestResultSerializer(serializers.ModelSerializer):
    job_id = serializers.CharField(source="job.id", read_only=True)

    class Meta:
        model = BacktestResult
        fields = [
            "id", "job_id", "framework", "strategy_name", "symbol",
            "timeframe", "timerange", "metrics", "trades", "config", "created_at",
        ]


class ScreenRequestSerializer(serializers.Serializer):
    symbol = serializers.CharField(default="BTC/USDT")
    timeframe = serializers.CharField(default="1h")
    exchange = serializers.CharField(default="binance")
    fees = serializers.FloatField(default=0.001)


class ScreenResultSerializer(serializers.ModelSerializer):
    job_id = serializers.CharField(source="job.id", read_only=True)

    class Meta:
        model = ScreenResult
        fields = [
            "id", "job_id", "symbol", "timeframe", "strategy_name",
            "top_results", "summary", "total_combinations", "created_at",
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
    exchange = serializers.CharField(default="binance")
    since_days = serializers.IntegerField(default=365)


class DataGenerateSampleRequestSerializer(serializers.Serializer):
    symbols = serializers.ListField(child=serializers.CharField(), default=["BTC/USDT", "ETH/USDT"])
    timeframes = serializers.ListField(child=serializers.CharField(), default=["1h"])
    days = serializers.IntegerField(default=90)


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
