from rest_framework import serializers

from market.constants import AssetClass
from portfolio.models import Holding, Portfolio


class HoldingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Holding
        fields = [
            "id",
            "portfolio_id",
            "symbol",
            "asset_class",
            "amount",
            "avg_buy_price",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "portfolio_id", "created_at", "updated_at"]


class HoldingCreateSerializer(serializers.Serializer):
    symbol = serializers.CharField(max_length=20)
    amount = serializers.FloatField(default=0.0)
    avg_buy_price = serializers.FloatField(default=0.0)
    asset_class = serializers.ChoiceField(
        choices=AssetClass.choices, default=AssetClass.CRYPTO,
    )


class PortfolioSerializer(serializers.ModelSerializer):
    holdings = HoldingSerializer(many=True, read_only=True)

    class Meta:
        model = Portfolio
        fields = [
            "id",
            "name",
            "exchange_id",
            "asset_class",
            "description",
            "holdings",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PortfolioCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    exchange_id = serializers.CharField(max_length=50, default="binance")
    description = serializers.CharField(max_length=500, default="", allow_blank=True)
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


class PortfolioUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    exchange_id = serializers.CharField(max_length=50, required=False)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)


class HoldingUpdateSerializer(serializers.Serializer):
    amount = serializers.FloatField(required=False)
    avg_buy_price = serializers.FloatField(required=False)


class PortfolioSummarySerializer(serializers.Serializer):
    total_value = serializers.FloatField()
    total_cost = serializers.FloatField()
    unrealized_pnl = serializers.FloatField()
    pnl_pct = serializers.FloatField()
    holding_count = serializers.IntegerField()
    currency = serializers.CharField()


class AllocationItemSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    amount = serializers.FloatField()
    current_price = serializers.FloatField()
    market_value = serializers.FloatField()
    cost_basis = serializers.FloatField()
    pnl = serializers.FloatField()
    pnl_pct = serializers.FloatField()
    weight = serializers.FloatField()
    price_stale = serializers.BooleanField()
