from rest_framework import serializers

from trading.models import Order


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            "id", "exchange_id", "exchange_order_id", "symbol", "side",
            "order_type", "amount", "price", "filled", "status", "timestamp",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "exchange_order_id", "filled", "status",
            "timestamp", "created_at", "updated_at",
        ]


class OrderCreateSerializer(serializers.Serializer):
    symbol = serializers.CharField(max_length=20)
    side = serializers.CharField(max_length=10)
    order_type = serializers.CharField(max_length=20, default="market")
    amount = serializers.FloatField()
    price = serializers.FloatField(default=0.0)
    exchange_id = serializers.CharField(max_length=50, default="binance")
