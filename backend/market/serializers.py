from rest_framework import serializers

from market.models import DataSourceConfig, ExchangeConfig, NewsArticle

# ── Exchange Config serializers ──────────────────────────────


def _mask_value(value: str) -> str:
    """Mask a credential value: show first4****last4, or **** if too short."""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


class ExchangeConfigSerializer(serializers.ModelSerializer):
    """Read serializer — never exposes raw credentials."""

    api_key_masked = serializers.SerializerMethodField()
    has_api_key = serializers.SerializerMethodField()
    has_api_secret = serializers.SerializerMethodField()
    has_passphrase = serializers.SerializerMethodField()

    class Meta:
        model = ExchangeConfig
        exclude = ["api_key", "api_secret", "passphrase"]

    def get_api_key_masked(self, obj) -> str:
        return _mask_value(obj.api_key)

    def get_has_api_key(self, obj) -> bool:
        return bool(obj.api_key)

    def get_has_api_secret(self, obj) -> bool:
        return bool(obj.api_secret)

    def get_has_passphrase(self, obj) -> bool:
        return bool(obj.passphrase)


class ExchangeConfigCreateSerializer(serializers.ModelSerializer):
    """Write serializer for creating exchange configs."""

    class Meta:
        model = ExchangeConfig
        fields = [
            "name",
            "exchange_id",
            "api_key",
            "api_secret",
            "passphrase",
            "is_sandbox",
            "is_default",
            "is_active",
            "options",
        ]


class ExchangeConfigUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for updating exchange configs — all fields optional."""

    class Meta:
        model = ExchangeConfig
        fields = [
            "name",
            "exchange_id",
            "api_key",
            "api_secret",
            "passphrase",
            "is_sandbox",
            "is_default",
            "is_active",
            "options",
        ]
        extra_kwargs = {f: {"required": False} for f in fields}

    def update(self, instance, validated_data):
        # Omitting credential fields preserves existing values
        for field in ("api_key", "api_secret", "passphrase"):
            if field not in validated_data:
                validated_data[field] = getattr(instance, field)
        return super().update(instance, validated_data)


class ExchangeConfigRotateSerializer(serializers.Serializer):
    """Serializer for key rotation — requires new credentials."""

    api_key = serializers.CharField(required=True)
    api_secret = serializers.CharField(required=True)
    passphrase = serializers.CharField(required=False, allow_blank=True, default="")


# ── Data Source Config serializers ───────────────────────────


class DataSourceConfigSerializer(serializers.ModelSerializer):
    exchange_name = serializers.CharField(source="exchange_config.name", read_only=True)

    class Meta:
        model = DataSourceConfig
        fields = "__all__"


class DataSourceConfigCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSourceConfig
        fields = [
            "exchange_config",
            "symbols",
            "timeframes",
            "is_active",
            "fetch_interval_minutes",
        ]


# ── Existing market serializers ──────────────────────────────


class ExchangeInfoSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    countries = serializers.ListField(child=serializers.CharField(), default=[])
    has_fetch_tickers = serializers.BooleanField(default=False)
    has_fetch_ohlcv = serializers.BooleanField(default=False)


class TickerDataSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    price = serializers.FloatField()
    volume_24h = serializers.FloatField(default=0.0)
    change_24h = serializers.FloatField(default=0.0)
    high_24h = serializers.FloatField(default=0.0)
    low_24h = serializers.FloatField(default=0.0)
    timestamp = serializers.DateTimeField()


class OHLCVDataSerializer(serializers.Serializer):
    timestamp = serializers.IntegerField()
    open = serializers.FloatField()
    high = serializers.FloatField()
    low = serializers.FloatField()
    close = serializers.FloatField()
    volume = serializers.FloatField()


class RegimeStateSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    regime = serializers.CharField()
    confidence = serializers.FloatField()
    adx_value = serializers.FloatField()
    bb_width_percentile = serializers.FloatField()
    ema_slope = serializers.FloatField()
    trend_alignment = serializers.FloatField()
    price_structure_score = serializers.FloatField()
    transition_probabilities = serializers.DictField(default={})


class RoutingDecisionSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    regime = serializers.CharField()
    confidence = serializers.FloatField()
    primary_strategy = serializers.CharField()
    weights = serializers.ListField()
    position_size_modifier = serializers.FloatField()
    reasoning = serializers.CharField()
    sentiment_modifier = serializers.FloatField(required=False, allow_null=True)


class RegimeHistoryEntrySerializer(serializers.Serializer):
    timestamp = serializers.CharField()
    regime = serializers.CharField()
    confidence = serializers.FloatField()
    adx_value = serializers.FloatField()
    bb_width_percentile = serializers.FloatField()


class RegimePositionSizeRequestSerializer(serializers.Serializer):
    symbol = serializers.RegexField(
        regex=r"^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$",
        max_length=20,
        help_text="Trading pair, e.g. BTC/USDT",
    )
    entry_price = serializers.FloatField(min_value=1e-8)
    stop_loss_price = serializers.FloatField(min_value=1e-8)


class RegimePositionSizeResponseSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    regime = serializers.CharField()
    regime_modifier = serializers.FloatField()
    position_size = serializers.FloatField()
    entry_price = serializers.FloatField()
    stop_loss_price = serializers.FloatField()
    primary_strategy = serializers.CharField()


class ExchangeTestResultSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    markets_count = serializers.IntegerField(required=False)
    message = serializers.CharField()


# ── News serializers ─────────────────────────────────────────


class NewsArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsArticle
        fields = [
            "article_id",
            "title",
            "url",
            "source",
            "summary",
            "published_at",
            "symbols",
            "asset_class",
            "sentiment_score",
            "sentiment_label",
            "created_at",
        ]


class NewsSentimentSummarySerializer(serializers.Serializer):
    asset_class = serializers.CharField()
    hours = serializers.IntegerField()
    total_articles = serializers.IntegerField()
    avg_score = serializers.FloatField()
    overall_label = serializers.CharField()
    positive_count = serializers.IntegerField()
    negative_count = serializers.IntegerField()
    neutral_count = serializers.IntegerField()


# ── OpenAPI response serializers ─────────────────────────────


class NewsFetchResponseSerializer(serializers.Serializer):
    asset_class = serializers.CharField()
    articles_fetched = serializers.IntegerField()
    message = serializers.CharField()


class MarketStatusSerializer(serializers.Serializer):
    asset_class = serializers.CharField()
    is_open = serializers.BooleanField()
    next_open = serializers.CharField(allow_null=True)
    next_close = serializers.CharField(allow_null=True)


class IndicatorInfoSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()


class CircuitBreakerStatusSerializer(serializers.Serializer):
    exchange_id = serializers.CharField()
    state = serializers.CharField()
    failure_count = serializers.IntegerField()


class CircuitBreakerListResponseSerializer(serializers.Serializer):
    breakers = CircuitBreakerStatusSerializer(many=True)


class CircuitBreakerResetSerializer(serializers.Serializer):
    message = serializers.CharField()


class KeyRotationResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    markets_count = serializers.IntegerField()
    message = serializers.CharField()
    key_rotated_at = serializers.CharField()


class SentimentSignalThresholdsSerializer(serializers.Serializer):
    bullish = serializers.FloatField()
    bearish = serializers.FloatField()


class SentimentSignalSerializer(serializers.Serializer):
    signal = serializers.FloatField()
    conviction = serializers.FloatField()
    signal_label = serializers.CharField()
    position_modifier = serializers.FloatField()
    article_count = serializers.IntegerField()
    avg_age_hours = serializers.FloatField()
    asset_class = serializers.CharField()
    thresholds = SentimentSignalThresholdsSerializer()
