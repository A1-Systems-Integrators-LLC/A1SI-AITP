from django.db import models


class Portfolio(models.Model):
    name = models.CharField(max_length=100)
    exchange_id = models.CharField(max_length=50, default="binance")
    description = models.CharField(max_length=500, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Holding(models.Model):
    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="holdings"
    )
    symbol = models.CharField(max_length=20)
    amount = models.FloatField(default=0.0)
    avg_buy_price = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.symbol} x{self.amount}"
