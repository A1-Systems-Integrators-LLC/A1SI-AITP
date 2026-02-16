from django.urls import path

from analysis.views import (
    BacktestCompareView,
    BacktestResultDetailView,
    BacktestResultListView,
    BacktestRunView,
    BacktestStrategyListView,
    DataDetailView,
    DataDownloadView,
    DataGenerateSampleView,
    DataListView,
    JobCancelView,
    JobDetailView,
    JobListView,
    ScreeningResultDetailView,
    ScreeningResultListView,
    ScreeningRunView,
    ScreeningStrategyListView,
)

urlpatterns = [
    # Jobs
    path("jobs/", JobListView.as_view(), name="job-list"),
    path("jobs/<str:job_id>/", JobDetailView.as_view(), name="job-detail"),
    path("jobs/<str:job_id>/cancel/", JobCancelView.as_view(), name="job-cancel"),
    # Backtest
    path("backtest/run/", BacktestRunView.as_view(), name="backtest-run"),
    path("backtest/results/", BacktestResultListView.as_view(), name="backtest-results"),
    path(
        "backtest/results/<int:result_id>/",
        BacktestResultDetailView.as_view(),
        name="backtest-result-detail",
    ),
    path("backtest/strategies/", BacktestStrategyListView.as_view(), name="backtest-strategies"),
    path("backtest/compare/", BacktestCompareView.as_view(), name="backtest-compare"),
    # Screening
    path("screening/run/", ScreeningRunView.as_view(), name="screening-run"),
    path("screening/results/", ScreeningResultListView.as_view(), name="screening-results"),
    path(
        "screening/results/<int:result_id>/",
        ScreeningResultDetailView.as_view(),
        name="screening-result-detail",
    ),
    path("screening/strategies/", ScreeningStrategyListView.as_view(), name="screening-strategies"),
    # Data pipeline
    path("data/", DataListView.as_view(), name="data-list"),
    path(
        "data/<str:exchange>/<str:symbol>/<str:timeframe>/",
        DataDetailView.as_view(), name="data-detail",
    ),
    path("data/download/", DataDownloadView.as_view(), name="data-download"),
    path("data/generate-sample/", DataGenerateSampleView.as_view(), name="data-generate-sample"),
]
