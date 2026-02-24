from django.core.exceptions import ValidationError
from django.db import models

from market.constants import AssetClass


class Portfolio(models.Model):
    # Design: single-user platform (Jetson deployment). No user FK — all
    # authenticated users share all portfolios. If multi-user support is
    # needed, add `user = models.ForeignKey(settings.AUTH_USER_MODEL, ...)`
    # and filter querysets by request.user in views.
    name = models.CharField(max_length=100)
    exchange_id = models.CharField(max_length=50, default="binance")
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
    )
    description = models.CharField(max_length=500, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Holding(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="holdings")
    symbol = models.CharField(max_length=20, db_index=True)
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
    )
    amount = models.FloatField(default=0.0)
    avg_buy_price = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["portfolio", "symbol"],
                name="idx_holding_portfolio_symbol",
            ),
        ]

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        if self.amount is not None and self.amount < 0:
            errors.setdefault("amount", []).append("Amount must be >= 0.")
        if self.avg_buy_price is not None and self.avg_buy_price < 0:
            errors.setdefault("avg_buy_price", []).append("avg_buy_price must be >= 0.")
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.symbol} x{self.amount}"
