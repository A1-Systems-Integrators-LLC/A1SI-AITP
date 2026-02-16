from rest_framework import serializers

from risk.models import AlertLog, RiskLimits, RiskMetricHistory, TradeCheckLog


class RiskLimitsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskLimits
        fields = [
            "max_portfolio_drawdown", "max_single_trade_risk", "max_daily_loss",
            "max_open_positions", "max_position_size_pct", "max_correlation",
            "min_risk_reward", "max_leverage",
        ]


class RiskLimitsUpdateSerializer(serializers.Serializer):
    max_portfolio_drawdown = serializers.FloatField(required=False)
    max_single_trade_risk = serializers.FloatField(required=False)
    max_daily_loss = serializers.FloatField(required=False)
    max_open_positions = serializers.IntegerField(required=False)
    max_position_size_pct = serializers.FloatField(required=False)
    max_correlation = serializers.FloatField(required=False)
    min_risk_reward = serializers.FloatField(required=False)
    max_leverage = serializers.FloatField(required=False)


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
    equity = serializers.FloatField()


class TradeCheckRequestSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    side = serializers.CharField()
    size = serializers.FloatField()
    entry_price = serializers.FloatField()
    stop_loss_price = serializers.FloatField(required=False, allow_null=True)


class TradeCheckResponseSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    reason = serializers.CharField()


class PositionSizeRequestSerializer(serializers.Serializer):
    entry_price = serializers.FloatField()
    stop_loss_price = serializers.FloatField()
    risk_per_trade = serializers.FloatField(required=False, allow_null=True)


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
            "id", "portfolio_id", "var_95", "var_99", "cvar_95", "cvar_99",
            "method", "drawdown", "equity", "open_positions_count", "recorded_at",
        ]


class HaltRequestSerializer(serializers.Serializer):
    reason = serializers.CharField()


class HaltResponseSerializer(serializers.Serializer):
    is_halted = serializers.BooleanField()
    halt_reason = serializers.CharField()
    message = serializers.CharField()


class AlertLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertLog
        fields = [
            "id", "portfolio_id", "event_type", "severity", "message",
            "channel", "delivered", "error", "created_at",
        ]


class TradeCheckLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeCheckLog
        fields = [
            "id", "portfolio_id", "symbol", "side", "size", "entry_price",
            "stop_loss_price", "approved", "reason", "equity_at_check",
            "drawdown_at_check", "open_positions_at_check", "checked_at",
        ]
