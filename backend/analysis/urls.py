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
    DataQualityDetailView,
    DataQualityListView,
    JobCancelView,
    JobDetailView,
    JobListView,
    MLModelDetailView,
    MLModelListView,
    MLPredictView,
    MLTrainView,
    ScreeningResultDetailView,
    ScreeningResultListView,
    ScreeningRunView,
    ScreeningStrategyListView,
    WorkflowDetailView,
    WorkflowDisableView,
    WorkflowEnableView,
    WorkflowListView,
    WorkflowRunCancelView,
    WorkflowRunDetailView,
    WorkflowRunListView,
    WorkflowStepTypesView,
    WorkflowTriggerView,
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
    # Data pipeline — static routes before parameterized
    path("data/", DataListView.as_view(), name="data-list"),
    path("data/download/", DataDownloadView.as_view(), name="data-download"),
    path("data/generate-sample/", DataGenerateSampleView.as_view(), name="data-generate-sample"),
    path("data/quality/", DataQualityListView.as_view(), name="data-quality-list"),
    path(
        "data/quality/<str:symbol>/<str:timeframe>/",
        DataQualityDetailView.as_view(),
        name="data-quality-detail",
    ),
    path(
        "data/<str:exchange>/<str:symbol>/<str:timeframe>/",
        DataDetailView.as_view(),
        name="data-detail",
    ),
    # ML
    path("ml/train/", MLTrainView.as_view(), name="ml-train"),
    path("ml/models/", MLModelListView.as_view(), name="ml-model-list"),
    path("ml/models/<str:model_id>/", MLModelDetailView.as_view(), name="ml-model-detail"),
    path("ml/predict/", MLPredictView.as_view(), name="ml-predict"),
    # Workflows
    path("workflows/", WorkflowListView.as_view(), name="workflow-list"),
    path("workflows/<str:workflow_id>/", WorkflowDetailView.as_view(), name="workflow-detail"),
    path(
        "workflows/<str:workflow_id>/trigger/",
        WorkflowTriggerView.as_view(), name="workflow-trigger",
    ),
    path(
        "workflows/<str:workflow_id>/enable/",
        WorkflowEnableView.as_view(), name="workflow-enable",
    ),
    path(
        "workflows/<str:workflow_id>/disable/",
        WorkflowDisableView.as_view(), name="workflow-disable",
    ),
    path(
        "workflows/<str:workflow_id>/runs/",
        WorkflowRunListView.as_view(), name="workflow-runs",
    ),
    path(
        "workflow-runs/<str:run_id>/",
        WorkflowRunDetailView.as_view(), name="workflow-run-detail",
    ),
    path(
        "workflow-runs/<str:run_id>/cancel/",
        WorkflowRunCancelView.as_view(), name="workflow-run-cancel",
    ),
    path("workflow-steps/", WorkflowStepTypesView.as_view(), name="workflow-step-types"),
]
