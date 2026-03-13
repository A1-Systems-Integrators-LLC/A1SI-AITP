from rest_framework import serializers

from market.constants import AssetClass
from risk.models import AlertLog, RiskLimitChange, RiskLimits, RiskMetricHistory, TradeCheckLog


class RiskLimitsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskLimits
        fields = [
            "max_portfolio_drawdown",
            "max_single_trade_risk",
            "max_daily_loss",
            "max_open_positions",
            "max_position_size_pct",
            "max_correlation",
            "min_risk_reward",
            "max_leverage",
        ]


class RiskLimitsUpdateSerializer(serializers.Serializer):
    max_portfolio_drawdown = serializers.FloatField(required=False, min_value=0.01, max_value=1.0)
    max_single_trade_risk = serializers.FloatField(required=False, min_value=0.001, max_value=1.0)
    max_daily_loss = serializers.FloatField(required=False, min_value=0.01, max_value=1.0)
    max_open_positions = serializers.IntegerField(required=False, min_value=1, max_value=100)
    max_position_size_pct = serializers.FloatField(required=False, min_value=0.01, max_value=1.0)
    max_correlation = serializers.FloatField(required=False, min_value=0.0, max_value=1.0)
    min_risk_reward = serializers.FloatField(required=False, min_value=0.1, max_value=100.0)
    max_leverage = serializers.FloatField(required=False, min_value=1.0, max_value=125.0)
    reason = serializers.CharField(required=False, max_length=500, default="")


class RiskStatusSerializer(serializers.Serializer):
    equity = serializers.FloatField()
    peak_equity = serializers.FloatField()
    drawdown = serializers.FloatField()
    daily_pnl = serializers.FloatField()
    total_pnl = serializers.FloatField()
    open_positions = serializers.IntegerField()
    is_halted = serializers.BooleanField()
    halt_reason = serializers.CharField()


class EquityUpdateSerializer(serializers.Serializer):
    equity = serializers.FloatField(min_value=0.0)


class TradeCheckRequestSerializer(serializers.Serializer):
    symbol = serializers.RegexField(
        regex=r"^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$",
        max_length=20,
        help_text="Trading pair, e.g. BTC/USDT",
    )
    side = serializers.ChoiceField(choices=["buy", "sell"])
    size = serializers.FloatField(min_value=1e-8)
    entry_price = serializers.FloatField(min_value=1e-8)
    stop_loss_price = serializers.FloatField(required=False, allow_null=True, min_value=0.0)
    asset_class = serializers.ChoiceField(
        choices=AssetClass.choices, default=AssetClass.CRYPTO,
    )
    composite_score = serializers.FloatField(
        required=False, allow_null=True, min_value=0, max_value=100,
        help_text="Conviction composite score (0-100) from SignalAggregator",
    )


class TradeCheckResponseSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    reason = serializers.CharField()
    composite_score = serializers.FloatField(required=False, allow_null=True)


class PositionSizeRequestSerializer(serializers.Serializer):
    entry_price = serializers.FloatField(min_value=1e-8)
    stop_loss_price = serializers.FloatField(min_value=1e-8)
    risk_per_trade = serializers.FloatField(
        required=False,
        allow_null=True,
        min_value=0.001,
        max_value=1.0,
    )


class PositionSizeResponseSerializer(serializers.Serializer):
    size = serializers.FloatField()
    risk_amount = serializers.FloatField()
    position_value = serializers.FloatField()


class VaRResponseSerializer(serializers.Serializer):
    var_95 = serializers.FloatField()
    var_99 = serializers.FloatField()
    cvar_95 = serializers.FloatField()
    cvar_99 = serializers.FloatField()
    method = serializers.CharField()
    window_days = serializers.IntegerField()


class HeatCheckResponseSerializer(serializers.Serializer):
    healthy = serializers.BooleanField()
    issues = serializers.ListField(child=serializers.CharField())
    drawdown = serializers.FloatField()
    daily_pnl = serializers.FloatField()
    open_positions = serializers.IntegerField()
    max_correlation = serializers.FloatField()
    high_corr_pairs = serializers.ListField()
    max_concentration = serializers.FloatField()
    position_weights = serializers.DictField()
    var_95 = serializers.FloatField()
    var_99 = serializers.FloatField()
    cvar_95 = serializers.FloatField()
    cvar_99 = serializers.FloatField()
    is_halted = serializers.BooleanField()


class RiskMetricHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskMetricHistory
        fields = [
            "id",
            "portfolio_id",
            "var_95",
            "var_99",
            "cvar_95",
            "cvar_99",
            "method",
            "drawdown",
            "equity",
            "open_positions_count",
            "recorded_at",
        ]


class HaltRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=1, max_length=500)


class HaltResponseSerializer(serializers.Serializer):
    is_halted = serializers.BooleanField()
    halt_reason = serializers.CharField()
    message = serializers.CharField()


class AlertLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertLog
        fields = [
            "id",
            "portfolio_id",
            "event_type",
            "severity",
            "message",
            "channel",
            "delivered",
            "error",
            "created_at",
        ]


class RiskLimitChangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskLimitChange
        fields = [
            "id",
            "portfolio_id",
            "field_name",
            "old_value",
            "new_value",
            "changed_by",
            "reason",
            "changed_at",
        ]


class TradeCheckLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeCheckLog
        fields = [
            "id",
            "portfolio_id",
            "symbol",
            "asset_class",
            "side",
            "size",
            "entry_price",
            "stop_loss_price",
            "approved",
            "reason",
            "equity_at_check",
            "drawdown_at_check",
            "open_positions_at_check",
            "composite_score",
            "checked_at",
        ]
