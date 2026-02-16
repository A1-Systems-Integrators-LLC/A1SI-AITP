from django.urls import path

from risk.views import (
    AlertListView,
    EquityUpdateView,
    HaltTradingView,
    HeatCheckView,
    MetricHistoryView,
    PositionSizeView,
    RecordMetricsView,
    ResetDailyView,
    ResumeTradingView,
    RiskLimitsView,
    RiskStatusView,
    TradeCheckView,
    TradeLogView,
    VaRView,
)

urlpatterns = [
    path("risk/<int:portfolio_id>/status/", RiskStatusView.as_view(), name="risk-status"),
    path("risk/<int:portfolio_id>/limits/", RiskLimitsView.as_view(), name="risk-limits"),
    path("risk/<int:portfolio_id>/equity/", EquityUpdateView.as_view(), name="risk-equity"),
    path("risk/<int:portfolio_id>/check-trade/", TradeCheckView.as_view(), name="risk-check-trade"),
    path(
        "risk/<int:portfolio_id>/position-size/",
        PositionSizeView.as_view(), name="risk-position-size",
    ),
    path("risk/<int:portfolio_id>/reset-daily/", ResetDailyView.as_view(), name="risk-reset-daily"),
    path("risk/<int:portfolio_id>/var/", VaRView.as_view(), name="risk-var"),
    path("risk/<int:portfolio_id>/heat-check/", HeatCheckView.as_view(), name="risk-heat-check"),
    path(
        "risk/<int:portfolio_id>/metric-history/",
        MetricHistoryView.as_view(),
        name="risk-metric-history",
    ),
    path(
        "risk/<int:portfolio_id>/record-metrics/",
        RecordMetricsView.as_view(),
        name="risk-record-metrics",
    ),
    path("risk/<int:portfolio_id>/halt/", HaltTradingView.as_view(), name="risk-halt"),
    path("risk/<int:portfolio_id>/resume/", ResumeTradingView.as_view(), name="risk-resume"),
    path("risk/<int:portfolio_id>/alerts/", AlertListView.as_view(), name="risk-alerts"),
    path("risk/<int:portfolio_id>/trade-log/", TradeLogView.as_view(), name="risk-trade-log"),
]
