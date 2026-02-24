from django.urls import path

from portfolio.views import (
    HoldingCreateView,
    HoldingDetailView,
    PortfolioAllocationView,
    PortfolioDetailView,
    PortfolioListView,
    PortfolioSummaryView,
)

urlpatterns = [
    path("portfolios/", PortfolioListView.as_view(), name="portfolio-list"),
    path("portfolios/<int:portfolio_id>/", PortfolioDetailView.as_view(), name="portfolio-detail"),
    path(
        "portfolios/<int:portfolio_id>/summary/",
        PortfolioSummaryView.as_view(),
        name="portfolio-summary",
    ),
    path(
        "portfolios/<int:portfolio_id>/allocation/",
        PortfolioAllocationView.as_view(),
        name="portfolio-allocation",
    ),
    path(
        "portfolios/<int:portfolio_id>/holdings/",
        HoldingCreateView.as_view(),
        name="holding-create",
    ),
    path(
        "portfolios/<int:portfolio_id>/holdings/<int:holding_id>/",
        HoldingDetailView.as_view(),
        name="holding-detail",
    ),
]
