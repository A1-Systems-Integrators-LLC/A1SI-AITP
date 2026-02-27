from rest_framework import serializers

from market.constants import AssetClass
from trading.models import Order, OrderFillEvent


class OrderFillEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderFillEvent
        fields = [
            "id",
            "fill_price",
            "fill_amount",
            "fee",
            "fee_currency",
            "exchange_trade_id",
            "filled_at",
        ]


class OrderSerializer(serializers.ModelSerializer):
    fill_events = OrderFillEventSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "exchange_id",
            "exchange_order_id",
            "symbol",
            "asset_class",
            "side",
            "order_type",
            "amount",
            "price",
            "filled",
            "status",
            "mode",
            "portfolio_id",
            "avg_fill_price",
            "stop_loss_price",
            "fee",
            "fee_currency",
            "reject_reason",
            "error_message",
            "timestamp",
            "submitted_at",
            "filled_at",
            "cancelled_at",
            "created_at",
            "updated_at",
            "fill_events",
        ]
        read_only_fields = [
            "id",
            "exchange_order_id",
            "filled",
            "status",
            "avg_fill_price",
            "fee",
            "fee_currency",
            "reject_reason",
            "error_message",
            "submitted_at",
            "filled_at",
            "cancelled_at",
            "timestamp",
            "created_at",
            "updated_at",
            "fill_events",
        ]


class CancelAllSerializer(serializers.Serializer):
    portfolio_id = serializers.IntegerField(min_value=1)


class CancelAllResponseSerializer(serializers.Serializer):
    cancelled_count = serializers.IntegerField()
    portfolio_id = serializers.IntegerField()


class ExchangeHealthSerializer(serializers.Serializer):
    exchange = serializers.CharField()
    connected = serializers.BooleanField()
    latency_ms = serializers.FloatField()
    last_checked = serializers.CharField()


class TradingPerformanceFilterSerializer(serializers.Serializer):
    portfolio_id = serializers.IntegerField(default=1, min_value=1)
    mode = serializers.ChoiceField(choices=["paper", "live"], required=False)
    asset_class = serializers.ChoiceField(
        choices=AssetClass.choices, required=False,
    )
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)


class TradingPerformanceSummarySerializer(serializers.Serializer):
    total_trades = serializers.IntegerField()
    win_count = serializers.IntegerField()
    loss_count = serializers.IntegerField()
    win_rate = serializers.FloatField()
    total_pnl = serializers.FloatField()
    avg_win = serializers.FloatField()
    avg_loss = serializers.FloatField()
    profit_factor = serializers.FloatField(allow_null=True)
    best_trade = serializers.FloatField()
    worst_trade = serializers.FloatField()


class SymbolPerformanceSerializer(TradingPerformanceSummarySerializer):
    symbol = serializers.CharField()


# ── OpenAPI response serializers ─────────────────────────────


class LiveTradingStatusSerializer(serializers.Serializer):
    exchange_connected = serializers.BooleanField()
    exchange_error = serializers.CharField(allow_blank=True)
    is_halted = serializers.BooleanField()
    active_live_orders = serializers.IntegerField()


class PaperTradingStatusResponseSerializer(serializers.Serializer):
    running = serializers.BooleanField()
    strategy = serializers.CharField(allow_null=True, required=False)
    started_at = serializers.CharField(allow_null=True, required=False)


class PaperTradingProfitSerializer(serializers.Serializer):
    total_profit = serializers.FloatField()


class OrderCreateSerializer(serializers.Serializer):
    symbol = serializers.RegexField(
        regex=r"^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$",
        max_length=20,
        min_length=5,
        help_text="Trading pair, e.g. BTC/USDT",
    )
    side = serializers.ChoiceField(choices=["buy", "sell"])
    order_type = serializers.ChoiceField(choices=["market", "limit"], default="market")
    amount = serializers.FloatField(min_value=1e-8)
    price = serializers.FloatField(default=0.0, min_value=0.0)
    exchange_id = serializers.CharField(max_length=50, default="kraken")
    mode = serializers.ChoiceField(choices=["paper", "live"], default="paper")
    portfolio_id = serializers.IntegerField(default=1, min_value=1)
    stop_loss_price = serializers.FloatField(required=False, allow_null=True, min_value=0.0)
    asset_class = serializers.ChoiceField(
        choices=AssetClass.choices, default=AssetClass.CRYPTO,
    )

    def validate_exchange_id(self, value: str) -> str:
        from market.models import EXCHANGE_CHOICES

        valid_ids = {choice[0] for choice in EXCHANGE_CHOICES}
        if value not in valid_ids:
            raise serializers.ValidationError(
                f"Invalid exchange_id '{value}'. Must be one of: {', '.join(sorted(valid_ids))}"
            )
        return value
