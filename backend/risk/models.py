from django.db import models


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


class TradeCheckLog(models.Model):
    portfolio_id = models.IntegerField(db_index=True)
    symbol = models.CharField(max_length=20)
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
