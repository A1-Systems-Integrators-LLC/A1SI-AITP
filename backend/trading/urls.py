from django.urls import path

from trading.views import (
    OrderDetailView,
    OrderListView,
    PaperTradingBalanceView,
    PaperTradingHistoryView,
    PaperTradingLogView,
    PaperTradingPerformanceView,
    PaperTradingProfitView,
    PaperTradingStartView,
    PaperTradingStatusView,
    PaperTradingStopView,
    PaperTradingTradesView,
)

urlpatterns = [
    path("trading/orders/", OrderListView.as_view(), name="order-list"),
    path("trading/orders/<int:order_id>/", OrderDetailView.as_view(), name="order-detail"),
    path("paper-trading/status/", PaperTradingStatusView.as_view(), name="paper-trading-status"),
    path("paper-trading/start/", PaperTradingStartView.as_view(), name="paper-trading-start"),
    path("paper-trading/stop/", PaperTradingStopView.as_view(), name="paper-trading-stop"),
    path("paper-trading/trades/", PaperTradingTradesView.as_view(), name="paper-trading-trades"),
    path("paper-trading/history/", PaperTradingHistoryView.as_view(), name="paper-trading-history"),
    path("paper-trading/profit/", PaperTradingProfitView.as_view(), name="paper-trading-profit"),
    path(
        "paper-trading/performance/",
        PaperTradingPerformanceView.as_view(),
        name="paper-trading-performance",
    ),
    path("paper-trading/balance/", PaperTradingBalanceView.as_view(), name="paper-trading-balance"),
    path("paper-trading/log/", PaperTradingLogView.as_view(), name="paper-trading-log"),
]
