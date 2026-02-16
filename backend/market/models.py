from django.db import models


class MarketData(models.Model):
    symbol = models.CharField(max_length=20, db_index=True)
    exchange_id = models.CharField(max_length=50)
    price = models.FloatField()
    volume_24h = models.FloatField(default=0.0)
    change_24h = models.FloatField(default=0.0)
    high_24h = models.FloatField(default=0.0)
    low_24h = models.FloatField(default=0.0)
    timestamp = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.symbol} @ {self.price}"
