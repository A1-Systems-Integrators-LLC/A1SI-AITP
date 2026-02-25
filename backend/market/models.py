from django.core.exceptions import ValidationError
from django.db import models

from market.constants import AssetClass
from market.fields import EncryptedTextField

EXCHANGE_CHOICES = [
    ("binance", "Binance"),
    ("coinbase", "Coinbase"),
    ("kraken", "Kraken"),
    ("kucoin", "KuCoin"),
    ("bybit", "Bybit"),
    ("yfinance", "Yahoo Finance"),
]


class MarketData(models.Model):
    symbol = models.CharField(max_length=20, db_index=True)
    exchange_id = models.CharField(max_length=50)
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
        db_index=True,
    )
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
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "exchange_id", "timestamp"],
                name="uniq_marketdata_symbol_exchange_ts",
            ),
        ]

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        if self.price is not None and self.price < 0:
            errors.setdefault("price", []).append("Price must be >= 0.")
        if self.volume_24h is not None and self.volume_24h < 0:
            errors.setdefault("volume_24h", []).append("Volume must be >= 0.")
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.symbol} @ {self.price}"


class ExchangeConfig(models.Model):
    name = models.CharField(max_length=100)
    exchange_id = models.CharField(max_length=50, choices=EXCHANGE_CHOICES)
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
    )
    api_key = EncryptedTextField(blank=True, default="")
    api_secret = EncryptedTextField(blank=True, default="")
    passphrase = EncryptedTextField(blank=True, default="")
    is_sandbox = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_success = models.BooleanField(null=True, blank=True)
    last_test_error = models.CharField(max_length=500, blank=True, default="")
    options = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    key_rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.name} ({self.exchange_id})"

    def save(self, *args, **kwargs):
        # Enforce at most one default
        if self.is_default:
            ExchangeConfig.objects.filter(is_default=True).exclude(pk=self.pk).update(
                is_default=False
            )
        super().save(*args, **kwargs)


class NewsArticle(models.Model):
    article_id = models.CharField(max_length=64, unique=True, db_index=True)
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=1000)
    source = models.CharField(max_length=100)
    summary = models.TextField(blank=True, default="")
    published_at = models.DateTimeField(db_index=True)
    symbols = models.JSONField(default=list, blank=True)
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
        db_index=True,
    )
    sentiment_score = models.FloatField(default=0.0)
    sentiment_label = models.CharField(max_length=10, default="neutral")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["asset_class", "-published_at"]),
        ]

    VALID_SENTIMENT_LABELS = {"positive", "negative", "neutral"}

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        if self.sentiment_score is not None and not (-1 <= self.sentiment_score <= 1):
            errors.setdefault("sentiment_score", []).append(
                "Sentiment score must be between -1 and 1."
            )
        if self.sentiment_label and self.sentiment_label not in self.VALID_SENTIMENT_LABELS:
            valid = ", ".join(sorted(self.VALID_SENTIMENT_LABELS))
            errors.setdefault("sentiment_label", []).append(
                f"Invalid label '{self.sentiment_label}'. Must be one of: {valid}."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"[{self.sentiment_label}] {self.title[:80]}"


class DataSourceConfig(models.Model):
    exchange_config = models.ForeignKey(
        ExchangeConfig, on_delete=models.CASCADE, related_name="data_sources",
        null=True, blank=True,
    )
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
    )
    symbols = models.JSONField(default=list)
    timeframes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    fetch_interval_minutes = models.IntegerField(default=60)
    last_fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        if not self.symbols:
            errors.setdefault("symbols", []).append("Symbols list must not be empty.")
        if self.fetch_interval_minutes is not None and self.fetch_interval_minutes <= 0:
            errors.setdefault("fetch_interval_minutes", []).append(
                "Fetch interval must be > 0."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"DataSource({self.exchange_config.name}: {self.symbols})"
