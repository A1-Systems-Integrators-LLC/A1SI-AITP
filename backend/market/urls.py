from django.urls import path

from market.views import (
    ExchangeListView,
    IndicatorComputeView,
    IndicatorListView,
    OHLCVView,
    RegimeCurrentAllView,
    RegimeCurrentView,
    RegimeHistoryView,
    RegimePositionSizeView,
    RegimeRecommendationAllView,
    RegimeRecommendationView,
    TickerListView,
    TickerView,
)

urlpatterns = [
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
]
