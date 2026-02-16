from rest_framework import serializers

from portfolio.models import Holding, Portfolio


class HoldingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Holding
        fields = [
            "id", "portfolio_id", "symbol", "amount",
            "avg_buy_price", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "portfolio_id", "created_at", "updated_at"]


class HoldingCreateSerializer(serializers.Serializer):
    symbol = serializers.CharField(max_length=20)
    amount = serializers.FloatField(default=0.0)
    avg_buy_price = serializers.FloatField(default=0.0)


class PortfolioSerializer(serializers.ModelSerializer):
    holdings = HoldingSerializer(many=True, read_only=True)

    class Meta:
        model = Portfolio
        fields = [
            "id", "name", "exchange_id", "description", "holdings",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PortfolioCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    exchange_id = serializers.CharField(max_length=50, default="binance")
    description = serializers.CharField(max_length=500, default="", allow_blank=True)
