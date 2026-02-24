from django.core.exceptions import ValidationError
from django.db import models

from market.constants import AssetClass


class RiskState(models.Model):
    portfolio_id = models.IntegerField(unique=True, db_index=True)
    total_equity = models.FloatField(default=10000.0)
    peak_equity = models.FloatField(default=10000.0)
    daily_start_equity = models.FloatField(default=10000.0)
    daily_pnl = models.FloatField(default=0.0)
    total_pnl = models.FloatField(default=0.0)
    open_positions = models.JSONField(default=dict, blank=True)
    is_halted = models.BooleanField(default=False)
    halt_reason = models.CharField(max_length=200, default="", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"RiskState(portfolio={self.portfolio_id}, equity={self.total_equity})"


class RiskLimits(models.Model):
    portfolio_id = models.IntegerField(unique=True, db_index=True)
    max_portfolio_drawdown = models.FloatField(default=0.15)
    max_single_trade_risk = models.FloatField(default=0.03)
    max_daily_loss = models.FloatField(default=0.05)
    max_open_positions = models.IntegerField(default=10)
    max_position_size_pct = models.FloatField(default=0.20)
    max_correlation = models.FloatField(default=0.70)
    min_risk_reward = models.FloatField(default=1.5)
    max_leverage = models.FloatField(default=1.0)

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        for field in ("max_portfolio_drawdown", "max_single_trade_risk", "max_daily_loss",
                       "max_position_size_pct", "max_correlation"):
            val = getattr(self, field, None)
            if val is not None and (val < 0 or val > 1):
                errors.setdefault(field, []).append(f"{field} must be between 0 and 1.")
        if self.max_open_positions is not None and self.max_open_positions < 0:
            errors.setdefault("max_open_positions", []).append(
                "max_open_positions must be >= 0."
            )
        if self.min_risk_reward is not None and self.min_risk_reward < 0:
            errors.setdefault("min_risk_reward", []).append(
                "min_risk_reward must be >= 0."
            )
        if self.max_leverage is not None and self.max_leverage < 0:
            errors.setdefault("max_leverage", []).append("max_leverage must be >= 0.")
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"RiskLimits(portfolio={self.portfolio_id})"


class RiskMetricHistory(models.Model):
    portfolio_id = models.IntegerField(db_index=True)
    var_95 = models.FloatField(default=0.0)
    var_99 = models.FloatField(default=0.0)
    cvar_95 = models.FloatField(default=0.0)
    cvar_99 = models.FloatField(default=0.0)
    method = models.CharField(max_length=20, default="parametric")
    drawdown = models.FloatField(default=0.0)
    equity = models.FloatField(default=0.0)
    open_positions_count = models.IntegerField(default=0)
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(
                fields=["portfolio_id", "recorded_at"],
                name="idx_risk_metric_portfolio_time",
            ),
        ]

    def __str__(self):
        return (
            f"RiskMetric(portfolio={self.portfolio_id},"
            f" VaR95={self.var_95:.4f}, {self.recorded_at})"
        )


class TradeCheckLog(models.Model):
    portfolio_id = models.IntegerField(db_index=True)
    symbol = models.CharField(max_length=20)
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
    )
    side = models.CharField(max_length=10)
    size = models.FloatField()
    entry_price = models.FloatField()
    stop_loss_price = models.FloatField(null=True, blank=True)
    approved = models.BooleanField()
    reason = models.CharField(max_length=500)
    equity_at_check = models.FloatField(default=0.0)
    drawdown_at_check = models.FloatField(default=0.0)
    open_positions_at_check = models.IntegerField(default=0)
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-checked_at"]
        indexes = [
            models.Index(
                fields=["portfolio_id", "-checked_at"],
                name="idx_tradecheck_portfolio_time",
            ),
        ]

    def __str__(self):
        verdict = "APPROVED" if self.approved else "REJECTED"
        return f"TradeCheck({self.symbol} {self.side} x{self.size} {verdict})"


class AlertLog(models.Model):
    portfolio_id = models.IntegerField(db_index=True)
    event_type = models.CharField(max_length=50)
    severity = models.CharField(max_length=20)
    message = models.TextField()
    channel = models.CharField(max_length=20, default="log")
    delivered = models.BooleanField(default=True)
    error = models.CharField(max_length=500, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["portfolio_id", "-created_at"],
                name="idx_alert_portfolio_created",
            ),
            models.Index(
                fields=["severity", "-created_at"],
                name="idx_alert_severity_created",
            ),
        ]

    def __str__(self):
        return f"Alert({self.severity} {self.event_type}: {self.message[:50]})"


class RiskLimitChange(models.Model):
    portfolio_id = models.IntegerField(db_index=True)
    field_name = models.CharField(max_length=50)
    old_value = models.CharField(max_length=50)
    new_value = models.CharField(max_length=50)
    changed_by = models.CharField(max_length=150, default="")
    reason = models.CharField(max_length=500, default="", blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        indexes = [
            models.Index(
                fields=["portfolio_id", "-changed_at"],
                name="idx_risklimitchange_port_time",
            ),
        ]

    def __str__(self):
        return (
            f"RiskLimitChange(portfolio={self.portfolio_id}, "
            f"{self.field_name}: {self.old_value} -> {self.new_value})"
        )
