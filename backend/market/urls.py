from django.urls import path

from market.views import (
    CircuitBreakerStatusView,
    DailyReportHistoryView,
    DailyReportView,
    DataSourceConfigDetailView,
    PDFReportDownloadView,
    PDFReportListView,
    DataSourceConfigListView,
    ExchangeConfigDetailView,
    ExchangeConfigListView,
    ExchangeConfigRotateView,
    ExchangeConfigTestView,
    ExchangeListView,
    IndicatorComputeView,
    IndicatorListView,
    MarketStatusView,
    NewsFetchView,
    NewsListView,
    NewsSentimentView,
    OHLCVView,
    OpportunityListView,
    OpportunitySummaryView,
    RegimeCurrentAllView,
    RegimeCurrentView,
    RegimeHistoryView,
    RegimePositionSizeView,
    RegimeRecommendationAllView,
    RegimeRecommendationView,
    SentimentSignalView,
    TickerListView,
    TickerView,
)

urlpatterns = [
    # Exchange config CRUD
    path("exchange-configs/", ExchangeConfigListView.as_view(), name="exchange-config-list"),
    path(
        "exchange-configs/<int:pk>/",
        ExchangeConfigDetailView.as_view(),
        name="exchange-config-detail",
    ),
    path(
        "exchange-configs/<int:pk>/test/",
        ExchangeConfigTestView.as_view(),
        name="exchange-config-test",
    ),
    path(
        "exchange-configs/<int:pk>/rotate/",
        ExchangeConfigRotateView.as_view(),
        name="exchange-config-rotate",
    ),
    # Data source config CRUD
    path("data-sources/", DataSourceConfigListView.as_view(), name="data-source-list"),
    path("data-sources/<int:pk>/", DataSourceConfigDetailView.as_view(), name="data-source-detail"),
    # Market status
    path("market/status/", MarketStatusView.as_view(), name="market-status"),
    # Existing routes
    path("exchanges/", ExchangeListView.as_view(), name="exchange-list"),
    path("market/ticker/<path:symbol>/", TickerView.as_view(), name="market-ticker"),
    path("market/tickers/", TickerListView.as_view(), name="market-tickers"),
    path("market/ohlcv/<path:symbol>/", OHLCVView.as_view(), name="market-ohlcv"),
    path("indicators/", IndicatorListView.as_view(), name="indicator-list"),
    path(
        "indicators/<str:exchange>/<str:symbol>/<str:timeframe>/",
        IndicatorComputeView.as_view(),
        name="indicator-compute",
    ),
    path("regime/current/", RegimeCurrentAllView.as_view(), name="regime-current-all"),
    path("regime/current/<path:symbol>/", RegimeCurrentView.as_view(), name="regime-current"),
    path("regime/history/<path:symbol>/", RegimeHistoryView.as_view(), name="regime-history"),
    path(
        "regime/recommendation/<path:symbol>/",
        RegimeRecommendationView.as_view(),
        name="regime-recommendation",
    ),
    path(
        "regime/recommendations/",
        RegimeRecommendationAllView.as_view(),
        name="regime-recommendations",
    ),
    path("regime/position-size/", RegimePositionSizeView.as_view(), name="regime-position-size"),
    # News
    path("market/news/", NewsListView.as_view(), name="news-list"),
    path("market/news/sentiment/", NewsSentimentView.as_view(), name="news-sentiment"),
    path("market/news/signal/", SentimentSignalView.as_view(), name="news-signal"),
    path("market/news/fetch/", NewsFetchView.as_view(), name="news-fetch"),
    # Circuit breaker
    path(
        "market/circuit-breaker/",
        CircuitBreakerStatusView.as_view(),
        name="circuit-breaker-status",
    ),
    # Market opportunities
    path("market/opportunities/", OpportunityListView.as_view(), name="opportunity-list"),
    path(
        "market/opportunities/summary/",
        OpportunitySummaryView.as_view(),
        name="opportunity-summary",
    ),
    # Daily report
    path("market/daily-report/", DailyReportView.as_view(), name="daily-report"),
    path(
        "market/daily-report/history/",
        DailyReportHistoryView.as_view(),
        name="daily-report-history",
    ),
    # PDF reports viewer
    path("market/reports/", PDFReportListView.as_view(), name="report-list"),
    path(
        "market/reports/<str:filename>/",
        PDFReportDownloadView.as_view(),
        name="report-download",
    ),
]
