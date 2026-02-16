from django.db import models


class Order(models.Model):
    exchange_id = models.CharField(max_length=50)
    exchange_order_id = models.CharField(max_length=100, default="", blank=True)
    symbol = models.CharField(max_length=20)
    side = models.CharField(max_length=10)  # buy / sell
    order_type = models.CharField(max_length=20)  # market / limit
    amount = models.FloatField()
    price = models.FloatField(default=0.0)
    filled = models.FloatField(default=0.0)
    status = models.CharField(max_length=20, default="pending")
    timestamp = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.side} {self.symbol} x{self.amount}"
