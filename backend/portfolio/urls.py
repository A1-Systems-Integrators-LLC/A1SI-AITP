from django.urls import path

from portfolio.views import HoldingCreateView, PortfolioDetailView, PortfolioListView

urlpatterns = [
    path("portfolios/", PortfolioListView.as_view(), name="portfolio-list"),
    path("portfolios/<int:portfolio_id>/", PortfolioDetailView.as_view(), name="portfolio-detail"),
    path(
        "portfolios/<int:portfolio_id>/holdings/",
        HoldingCreateView.as_view(), name="holding-create",
    ),
]
