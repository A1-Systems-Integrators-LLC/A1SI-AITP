from rest_framework import serializers


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


class RegimeHistoryEntrySerializer(serializers.Serializer):
    timestamp = serializers.CharField()
    regime = serializers.CharField()
    confidence = serializers.FloatField()
    adx_value = serializers.FloatField()
    bb_width_percentile = serializers.FloatField()


class RegimePositionSizeRequestSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    entry_price = serializers.FloatField()
    stop_loss_price = serializers.FloatField()


class RegimePositionSizeResponseSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    regime = serializers.CharField()
    regime_modifier = serializers.FloatField()
    position_size = serializers.FloatField()
    entry_price = serializers.FloatField()
    stop_loss_price = serializers.FloatField()
    primary_strategy = serializers.CharField()
