from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from market.constants import AssetClass


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUBMITTED = "submitted", "Submitted"
    OPEN = "open", "Open"
    PARTIAL_FILL = "partial_fill", "Partially Filled"
    FILLED = "filled", "Filled"
    CANCELLED = "cancelled", "Cancelled"
    REJECTED = "rejected", "Rejected"
    ERROR = "error", "Error"


class TradingMode(models.TextChoices):
    PAPER = "paper", "Paper"
    LIVE = "live", "Live"


# Valid state transitions for the order lifecycle
VALID_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PENDING: {
        OrderStatus.SUBMITTED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.ERROR,
    },
    OrderStatus.SUBMITTED: {
        OrderStatus.OPEN,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.ERROR,
    },
    OrderStatus.OPEN: {
        OrderStatus.PARTIAL_FILL,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.ERROR,
    },
    OrderStatus.PARTIAL_FILL: {
        OrderStatus.PARTIAL_FILL,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.ERROR,
    },
    # Terminal states — no transitions out
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.ERROR: set(),
}


class Order(models.Model):
    exchange_id = models.CharField(max_length=50)
    exchange_order_id = models.CharField(max_length=100, default="", blank=True)
    symbol = models.CharField(max_length=20)
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.CRYPTO,
    )
    side = models.CharField(max_length=10)  # buy / sell
    order_type = models.CharField(max_length=20)  # market / limit
    amount = models.FloatField()
    price = models.FloatField(default=0.0)
    filled = models.FloatField(default=0.0)
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True,
    )
    mode = models.CharField(
        max_length=10,
        choices=TradingMode.choices,
        default=TradingMode.PAPER,
        db_index=True,
    )
    portfolio_id = models.IntegerField(default=1)
    avg_fill_price = models.FloatField(default=0.0)
    stop_loss_price = models.FloatField(null=True, blank=True)
    fee = models.FloatField(default=0.0)
    fee_currency = models.CharField(max_length=20, default="", blank=True)
    reject_reason = models.CharField(max_length=500, default="", blank=True)
    error_message = models.CharField(max_length=500, default="", blank=True)
    timestamp = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    filled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(
                fields=["exchange_id", "exchange_order_id"],
                name="idx_order_exchange",
            ),
            models.Index(
                fields=["symbol", "status"],
                name="idx_order_symbol_status",
            ),
            models.Index(
                fields=["asset_class", "symbol"],
                name="idx_order_asset_symbol",
            ),
            models.Index(
                fields=["portfolio_id", "status", "-timestamp"],
                name="idx_order_portfolio_status_ts",
            ),
            models.Index(
                fields=["-created_at"],
                name="idx_order_created_desc",
            ),
        ]

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}
        if self.amount is not None and self.amount <= 0:
            errors.setdefault("amount", []).append("Amount must be greater than 0.")
        if self.price is not None and self.price < 0:
            errors.setdefault("price", []).append("Price must be >= 0.")
        if self.order_type == "limit" and (self.price is None or self.price <= 0):
            errors.setdefault("price", []).append("Limit orders require a price > 0.")
        if self.side not in ("buy", "sell"):
            errors.setdefault("side", []).append("Side must be 'buy' or 'sell'.")
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.side} {self.symbol} x{self.amount} [{self.status}]"

    def transition_to(self, new_status: str, **kwargs) -> None:
        """Validate and apply a state transition.

        Raises ValueError if the transition is not allowed.
        Extra kwargs are set as attributes (e.g. error_message, reject_reason).
        """
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(f"Invalid transition: {self.status} -> {new_status}")

        self.status = new_status
        now = timezone.now()

        if new_status == OrderStatus.SUBMITTED:
            self.submitted_at = now
        elif new_status == OrderStatus.FILLED:
            self.filled_at = now
        elif new_status == OrderStatus.CANCELLED:
            self.cancelled_at = now

        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        self.save()


class OrderFillEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="fill_events")
    fill_price = models.FloatField()
    fill_amount = models.FloatField()
    fee = models.FloatField(default=0.0)
    fee_currency = models.CharField(max_length=20, default="", blank=True)
    exchange_trade_id = models.CharField(max_length=100, default="", blank=True)
    filled_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-filled_at"]

    def __str__(self):
        return f"Fill {self.fill_amount}@{self.fill_price} for Order#{self.order_id}"
