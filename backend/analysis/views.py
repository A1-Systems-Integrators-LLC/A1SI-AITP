"""Analysis views — jobs, backtest, screening, data pipeline, ML, workflows, signals."""

import csv

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from analysis.models import (
    BackgroundJob,
    BacktestResult,
    MLModelPerformance,
    MLPrediction,
    ScreenResult,
    SignalAttribution,
    Workflow,
    WorkflowRun,
)
from analysis.serializers import (
    BackfillOutcomeRequestSerializer,
    BacktestComparisonSerializer,
    BacktestRequestSerializer,
    BacktestResultSerializer,
    CompositeSignalResponseSerializer,
    DataDownloadRequestSerializer,
    DataFileInfoSerializer,
    DataGenerateSampleRequestSerializer,
    DataQualityReportSerializer,
    DataQualitySummarySerializer,
    EntryCheckRequestSerializer,
    EntryCheckResponseSerializer,
    JobAcceptedSerializer,
    JobCancelResponseSerializer,
    JobSerializer,
    MLModelInfoSerializer,
    MLModelPerformanceSerializer,
    MLPredictionResponseSerializer,
    MLPredictionSerializer,
    MLPredictRequestSerializer,
    MLTrainRequestSerializer,
    RecordAttributionRequestSerializer,
    ScreenRequestSerializer,
    ScreenResultSerializer,
    SignalAttributionSerializer,
    SignalBatchRequestSerializer,
    SourceAccuracyResponseSerializer,
    StrategyInfoSerializer,
    StrategyStatusSerializer,
    WeightRecommendationResponseSerializer,
    WorkflowCreateSerializer,
    WorkflowDetailSerializer,
    WorkflowListSerializer,
    WorkflowRunDetailSerializer,
    WorkflowRunListSerializer,
    WorkflowScheduleResponseSerializer,
    WorkflowTriggerResponseSerializer,
)
from core.internal_auth import InternalAPIView
from core.utils import safe_int as _safe_int


class JobListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=JobSerializer(many=True), tags=["Jobs"])
    def get(self, request: Request) -> Response:
        job_type = request.query_params.get("job_type")
        limit = _safe_int(request.query_params.get("limit"), 50, max_val=200)
        qs = BackgroundJob.objects.all()
        if job_type:
            qs = qs.filter(job_type=job_type)
        jobs = qs[:limit]
        return Response(JobSerializer(jobs, many=True).data)


class JobDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=JobSerializer, tags=["Jobs"])
    def get(self, request: Request, job_id: str) -> Response:
        try:
            job = BackgroundJob.objects.get(id=job_id)
        except BackgroundJob.DoesNotExist:
            return Response({"error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)

        data = JobSerializer(job).data
        # Overlay live progress if available
        from analysis.services.job_runner import get_job_runner

        live = get_job_runner().get_live_progress(job_id)
        if live and job.status in ("pending", "running"):
            data["progress"] = live["progress"]
            data["progress_message"] = live["progress_message"]
        return Response(data)


class JobCancelView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=JobCancelResponseSerializer, tags=["Jobs"])
    def post(self, request: Request, job_id: str) -> Response:
        from analysis.services.job_runner import get_job_runner

        cancelled = get_job_runner().cancel_job(job_id)
        if not cancelled:
            return Response(
                {"error": "Job not found or not cancellable"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"status": "cancelled"})


class BacktestRunView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=BacktestRequestSerializer,
        responses=JobAcceptedSerializer,
        tags=["Backtest"],
    )
    def post(self, request: Request) -> Response:
        ser = BacktestRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from analysis.services.backtest import BacktestService
        from analysis.services.job_runner import get_job_runner

        job_id = get_job_runner().submit(
            job_type="backtest",
            run_fn=BacktestService.run_backtest,
            params=ser.validated_data,
        )
        return Response(
            {"job_id": job_id, "status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )


class BacktestResultListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=BacktestResultSerializer(many=True),
        tags=["Backtest"],
        parameters=[
            OpenApiParameter("limit", int, description="Max results (default 20, max 100)"),
            OpenApiParameter(
                "asset_class",
                str,
                description="Filter by asset class",
                enum=["crypto", "equity", "forex"],
            ),
        ],
    )
    def get(self, request: Request) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 20, max_val=100)
        asset_class = request.query_params.get("asset_class")
        qs = BacktestResult.objects.select_related("job").all()
        if asset_class in ("crypto", "equity", "forex"):
            qs = qs.filter(asset_class=asset_class)
        results = qs[:limit]
        return Response(BacktestResultSerializer(results, many=True).data)


class BacktestResultDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=BacktestResultSerializer, tags=["Backtest"])
    def get(self, request: Request, result_id: int) -> Response:
        try:
            result = BacktestResult.objects.select_related("job").get(id=result_id)
        except BacktestResult.DoesNotExist:
            return Response(
                {"error": "Backtest result not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(BacktestResultSerializer(result).data)


class BacktestStrategyListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=StrategyInfoSerializer(many=True), tags=["Backtest"])
    def get(self, request: Request) -> Response:
        from analysis.services.backtest import BacktestService

        return Response(BacktestService.list_strategies())


class BacktestCompareView(APIView):
    permission_classes = [IsAuthenticated]

    COMPARE_METRICS = [
        "total_return",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "profit_factor",
        "total_trades",
    ]
    # Metrics where lower is better
    LOWER_IS_BETTER = {"max_drawdown"}

    @extend_schema(responses=BacktestComparisonSerializer, tags=["Backtest"])
    def get(self, request: Request) -> Response:
        ids_param = request.query_params.get("ids", "")
        id_list = []
        for x in ids_param.split(","):
            x = x.strip()
            if x.isdigit():
                id_list.append(int(x))
        results = list(BacktestResult.objects.select_related("job").filter(id__in=id_list))

        if len(results) < 2:
            return Response(
                BacktestResultSerializer(results, many=True).data,
            )

        # Build comparison
        metrics_table = []
        rankings: dict[str, dict[str, int]] = {}
        best_per_metric: dict[str, str | None] = {}

        for metric_name in self.COMPARE_METRICS:
            values: dict[str, float | None] = {}
            for r in results:
                key = f"{r.strategy_name} (#{r.id})"
                raw = r.metrics.get(metric_name) if r.metrics else None
                values[key] = float(raw) if raw is not None else None

            # Rank non-null values
            valid = {k: v for k, v in values.items() if v is not None}
            lower_better = metric_name in self.LOWER_IS_BETTER
            sorted_keys = sorted(valid, key=lambda k: valid[k], reverse=not lower_better)
            rank_map = {k: i + 1 for i, k in enumerate(sorted_keys)}
            # Assign worst rank to nulls
            for k in values:
                if k not in rank_map:
                    rank_map[k] = len(values)

            best = sorted_keys[0] if sorted_keys else None

            metrics_table.append(
                {
                    "metric": metric_name,
                    "values": values,
                    "best": best,
                    "rankings": rank_map,
                },
            )
            rankings[metric_name] = rank_map
            best_per_metric[metric_name] = best

        # Overall best: lowest average rank
        all_keys = [f"{r.strategy_name} (#{r.id})" for r in results]
        avg_ranks = {}
        for key in all_keys:
            ranks = [rankings[m].get(key, len(all_keys)) for m in self.COMPARE_METRICS]
            avg_ranks[key] = sum(ranks) / len(ranks) if ranks else float("inf")
        best_strategy = min(avg_ranks, key=avg_ranks.get) if avg_ranks else None

        comparison = {
            "metrics_table": metrics_table,
            "best_strategy": best_strategy,
            "rankings": rankings,
        }

        return Response(
            {
                "results": BacktestResultSerializer(results, many=True).data,
                "comparison": comparison,
            },
        )


class BacktestExportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Backtest"], exclude=True)
    def get(self, request: Request) -> HttpResponse:
        qs = BacktestResult.objects.select_related("job").all()

        # Filters
        asset_class = request.query_params.get("asset_class")
        if asset_class in ("crypto", "equity", "forex"):
            qs = qs.filter(asset_class=asset_class)

        framework = request.query_params.get("framework")
        if framework:
            qs = qs.filter(framework__icontains=framework)

        strategy = request.query_params.get("strategy")
        if strategy:
            qs = qs.filter(strategy_name__icontains=strategy)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="backtest_results.csv"'

        writer = csv.writer(response)
        headers = [
            "id",
            "framework",
            "asset_class",
            "strategy_name",
            "symbol",
            "timeframe",
            "timerange",
            "total_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "profit_factor",
            "total_trades",
            "created_at",
        ]
        writer.writerow(headers)

        for r in qs:
            metrics = r.metrics or {}
            writer.writerow(
                [
                    r.id,
                    r.framework,
                    r.asset_class,
                    r.strategy_name,
                    r.symbol,
                    r.timeframe,
                    r.timerange,
                    metrics.get("total_return", ""),
                    metrics.get("sharpe_ratio", ""),
                    metrics.get("max_drawdown", ""),
                    metrics.get("win_rate", ""),
                    metrics.get("profit_factor", ""),
                    metrics.get("total_trades", ""),
                    r.created_at.isoformat() if r.created_at else "",
                ],
            )

        return response


class ScreeningRunView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ScreenRequestSerializer,
        responses=JobAcceptedSerializer,
        tags=["Screening"],
    )
    def post(self, request: Request) -> Response:
        ser = ScreenRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from analysis.services.job_runner import get_job_runner
        from analysis.services.screening import ScreenerService

        job_id = get_job_runner().submit(
            job_type="screening",
            run_fn=ScreenerService.run_full_screen,
            params=ser.validated_data,
        )
        return Response(
            {"job_id": job_id, "status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )


class ScreeningResultListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ScreenResultSerializer(many=True), tags=["Screening"])
    def get(self, request: Request) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 20, max_val=100)
        asset_class = request.query_params.get("asset_class")
        qs = ScreenResult.objects.select_related("job").all()
        if asset_class in ("crypto", "equity", "forex"):
            qs = qs.filter(asset_class=asset_class)
        results = qs[:limit]
        return Response(ScreenResultSerializer(results, many=True).data)


class ScreeningResultDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ScreenResultSerializer, tags=["Screening"])
    def get(self, request: Request, result_id: int) -> Response:
        try:
            result = ScreenResult.objects.select_related("job").get(id=result_id)
        except ScreenResult.DoesNotExist:
            return Response({"error": "Screen result not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(ScreenResultSerializer(result).data)


class ScreeningStrategyListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Screening"])
    def get(self, request: Request) -> Response:
        from analysis.services.screening import STRATEGY_TYPES

        return Response(STRATEGY_TYPES)


class DataListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=DataFileInfoSerializer(many=True), tags=["Data"])
    def get(self, request: Request) -> Response:
        from analysis.services.data_pipeline import DataPipelineService

        svc = DataPipelineService()
        return Response(svc.list_available_data())


class DataDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=DataFileInfoSerializer, tags=["Data"])
    def get(self, request: Request, exchange: str, symbol: str, timeframe: str) -> Response:
        from analysis.services.data_pipeline import DataPipelineService

        real_symbol = symbol.replace("_", "/")
        svc = DataPipelineService()
        info = svc.get_data_info(real_symbol, timeframe, exchange)
        if not info:
            return Response({"error": "Data file not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(info)


class DataDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=DataDownloadRequestSerializer,
        responses=JobAcceptedSerializer,
        tags=["Data"],
    )
    def post(self, request: Request) -> Response:
        from analysis.services.data_pipeline import DataPipelineService
        from analysis.services.job_runner import get_job_runner

        ser = DataDownloadRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        job_id = get_job_runner().submit(
            job_type="data_download",
            run_fn=DataPipelineService.download_data,
            params=ser.validated_data,
        )
        return Response(
            {"job_id": job_id, "status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )


class DataGenerateSampleView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=DataGenerateSampleRequestSerializer,
        responses=JobAcceptedSerializer,
        tags=["Data"],
    )
    def post(self, request: Request) -> Response:
        from analysis.services.data_pipeline import DataPipelineService
        from analysis.services.job_runner import get_job_runner

        ser = DataGenerateSampleRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        job_id = get_job_runner().submit(
            job_type="data_generate_sample",
            run_fn=DataPipelineService.generate_sample_data,
            params=ser.validated_data,
        )
        return Response(
            {"job_id": job_id, "status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )


# ──────────────────────────────────────────────
# ML endpoints
# ──────────────────────────────────────────────


class MLTrainView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=MLTrainRequestSerializer,
        responses=JobAcceptedSerializer,
        tags=["ML"],
    )
    def post(self, request: Request) -> Response:
        from analysis.services.job_runner import get_job_runner
        from analysis.services.ml import MLService

        ser = MLTrainRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        job_id = get_job_runner().submit(
            job_type="ml_train",
            run_fn=MLService.train,
            params=ser.validated_data,
        )
        return Response(
            {"job_id": job_id, "status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )


class MLModelListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MLModelInfoSerializer(many=True), tags=["ML"])
    def get(self, request: Request) -> Response:
        from analysis.services.ml import MLService

        return Response(MLService.list_models())


class MLModelDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MLModelInfoSerializer, tags=["ML"])
    def get(self, request: Request, model_id: str) -> Response:
        from analysis.services.ml import MLService

        detail = MLService.get_model_detail(model_id)
        if detail is None:
            return Response({"error": "Model not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(detail)


class MLPredictView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=MLPredictRequestSerializer,
        responses=MLPredictionResponseSerializer,
        tags=["ML"],
    )
    def post(self, request: Request) -> Response:
        from analysis.services.ml import MLService

        ser = MLPredictRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = MLService.predict(ser.validated_data)
        if "error" in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


# ── Data Quality views ─────────────────────────────────────


class DataQualityListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=DataQualitySummarySerializer, tags=["Data"])
    def get(self, request: Request) -> Response:
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        try:
            from common.data_pipeline.pipeline import validate_all_data

            reports = validate_all_data()
            report_dicts = [_quality_report_to_dict(r) for r in reports]
            passed = sum(1 for r in reports if r.passed)
            return Response(
                {
                    "total": len(reports),
                    "passed": passed,
                    "failed": len(reports) - passed,
                    "reports": report_dicts,
                },
            )
        except ImportError as e:
            return Response(
                {"error": f"Data quality module not available: {e}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except (OSError, ValueError) as e:
            return Response(
                {"error": f"Data quality check failed: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DataQualityDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=DataQualityReportSerializer, tags=["Data"])
    def get(self, request: Request, symbol: str, timeframe: str) -> Response:
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        real_symbol = symbol.replace("_", "/")
        exchange = request.query_params.get("exchange", "kraken")
        try:
            from common.data_pipeline.pipeline import validate_data

            report = validate_data(real_symbol, timeframe, exchange)
            return Response(_quality_report_to_dict(report))
        except FileNotFoundError:
            return Response(
                {"error": "Data file not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ImportError as e:
            return Response(
                {"error": f"Data quality module not available: {e}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except (OSError, ValueError) as e:
            return Response(
                {"error": f"Quality check failed: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


def _quality_report_to_dict(report: object) -> dict:
    """Convert DataQualityReport dataclass to dict."""
    return {
        "symbol": report.symbol,
        "timeframe": report.timeframe,
        "exchange": report.exchange,
        "rows": report.rows,
        "date_range": list(report.date_range),
        "gaps": report.gaps,
        "nan_columns": report.nan_columns,
        "outliers": report.outliers,
        "ohlc_violations": report.ohlc_violations,
        "is_stale": report.is_stale,
        "stale_hours": round(report.stale_hours, 1),
        "passed": report.passed,
        "issues_summary": report.issues_summary,
    }


# ── Workflow views ───────────────────────────────────────────


class WorkflowListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WorkflowListSerializer(many=True), tags=["Workflows"])
    def get(self, request: Request) -> Response:
        qs = Workflow.objects.prefetch_related("steps").all()
        asset_class = request.query_params.get("asset_class")
        if asset_class in ("crypto", "equity", "forex"):
            qs = qs.filter(asset_class=asset_class)
        return Response(WorkflowListSerializer(qs, many=True).data)

    @extend_schema(
        request=WorkflowCreateSerializer,
        responses=WorkflowDetailSerializer,
        tags=["Workflows"],
    )
    def post(self, request: Request) -> Response:
        from analysis.models import WorkflowStep

        ser = WorkflowCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        if Workflow.objects.filter(id=data["id"]).exists():
            return Response(
                {"error": f"Workflow '{data['id']}' already exists"},
                status=status.HTTP_409_CONFLICT,
            )

        wf = Workflow.objects.create(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            asset_class=data.get("asset_class", "crypto"),
            params=data.get("params", {}),
            schedule_interval_seconds=data.get("schedule_interval_seconds"),
            schedule_enabled=data.get("schedule_enabled", False),
        )
        for step_data in data["steps"]:
            WorkflowStep.objects.create(workflow=wf, **step_data)

        return Response(
            WorkflowDetailSerializer(wf).data,
            status=status.HTTP_201_CREATED,
        )


class WorkflowDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WorkflowDetailSerializer, tags=["Workflows"])
    def get(self, request: Request, workflow_id: str) -> Response:
        try:
            wf = Workflow.objects.prefetch_related("steps").get(id=workflow_id)
        except Workflow.DoesNotExist:
            return Response({"error": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(WorkflowDetailSerializer(wf).data)

    @extend_schema(responses={204: None}, tags=["Workflows"])
    def delete(self, request: Request, workflow_id: str) -> Response:
        try:
            wf = Workflow.objects.get(id=workflow_id)
        except Workflow.DoesNotExist:
            return Response({"error": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND)
        if wf.is_template:
            return Response(
                {"error": "Cannot delete template workflows"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        wf.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkflowTriggerView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WorkflowTriggerResponseSerializer, tags=["Workflows"])
    def post(self, request: Request, workflow_id: str) -> Response:
        from analysis.services.workflow_engine import WorkflowEngine

        try:
            run_id, job_id = WorkflowEngine.trigger(
                workflow_id,
                trigger="api",
                params=request.data.get("params"),
            )
        except Workflow.DoesNotExist:
            return Response({"error": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"workflow_run_id": run_id, "job_id": job_id},
            status=status.HTTP_202_ACCEPTED,
        )


class WorkflowEnableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WorkflowScheduleResponseSerializer, tags=["Workflows"])
    def post(self, request: Request, workflow_id: str) -> Response:
        try:
            wf = Workflow.objects.get(id=workflow_id)
        except Workflow.DoesNotExist:
            return Response({"error": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND)
        wf.schedule_enabled = True
        wf.save(update_fields=["schedule_enabled", "updated_at"])
        return Response({"status": "enabled", "workflow_id": workflow_id})


class WorkflowDisableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WorkflowScheduleResponseSerializer, tags=["Workflows"])
    def post(self, request: Request, workflow_id: str) -> Response:
        try:
            wf = Workflow.objects.get(id=workflow_id)
        except Workflow.DoesNotExist:
            return Response({"error": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND)
        wf.schedule_enabled = False
        wf.save(update_fields=["schedule_enabled", "updated_at"])
        return Response({"status": "disabled", "workflow_id": workflow_id})


class WorkflowRunListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WorkflowRunListSerializer(many=True), tags=["Workflows"])
    def get(self, request: Request, workflow_id: str) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 20, max_val=100)
        runs = WorkflowRun.objects.filter(
            workflow_id=workflow_id,
        ).select_related("workflow", "job")[:limit]
        return Response(WorkflowRunListSerializer(runs, many=True).data)


class WorkflowRunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WorkflowRunDetailSerializer, tags=["Workflows"])
    def get(self, request: Request, run_id: str) -> Response:
        try:
            run = (
                WorkflowRun.objects.select_related(
                    "workflow",
                    "job",
                )
                .prefetch_related(
                    "step_runs__step",
                )
                .get(id=run_id)
            )
        except WorkflowRun.DoesNotExist:
            return Response({"error": "Workflow run not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(WorkflowRunDetailSerializer(run).data)


class WorkflowRunCancelView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=JobCancelResponseSerializer, tags=["Workflows"])
    def post(self, request: Request, run_id: str) -> Response:
        from analysis.services.workflow_engine import WorkflowEngine

        cancelled = WorkflowEngine.cancel(run_id)
        if not cancelled:
            return Response(
                {"error": "Run not found or not cancellable"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"status": "cancelled"})


class WorkflowStepTypesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Workflows"])
    def get(self, request: Request) -> Response:
        from analysis.services.step_registry import get_step_types

        return Response(get_step_types())


# ── Signal views ─────────────────────────────────────────────


class SignalDetailView(APIView):
    """Composite conviction signal for a single symbol."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=CompositeSignalResponseSerializer,
        tags=["Signals"],
        parameters=[
            OpenApiParameter(
                "asset_class", str, description="Asset class",
                enum=["crypto", "equity", "forex"],
            ),
            OpenApiParameter("strategy", str, description="Strategy name"),
        ],
    )
    def get(self, request: Request, symbol: str) -> Response:
        from analysis.services.signal_service import SignalService

        real_symbol = symbol.replace("-", "/")
        asset_class = request.query_params.get("asset_class", "crypto")
        strategy = request.query_params.get("strategy", "CryptoInvestorV1")

        try:
            signal = SignalService.get_signal(real_symbol, asset_class, strategy)
            return Response(signal)
        except Exception as e:
            return Response(
                {"error": f"Signal computation failed: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SignalBatchView(APIView):
    """Batch composite signals for multiple symbols."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=SignalBatchRequestSerializer,
        responses=CompositeSignalResponseSerializer(many=True),
        tags=["Signals"],
    )
    def post(self, request: Request) -> Response:
        from analysis.services.signal_service import SignalService

        ser = SignalBatchRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        results = SignalService.get_signals_batch(
            symbols=data["symbols"],
            asset_class=data.get("asset_class", "crypto"),
            strategy_name=data.get("strategy_name", "CryptoInvestorV1"),
        )
        return Response(results)


class SignalHealthView(InternalAPIView):
    """Signal pipeline health: per-source availability and latency."""

    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        tags=["Signals"],
        parameters=[
            OpenApiParameter(
                "asset_class", str, enum=["crypto", "equity", "forex"],
            ),
        ],
    )
    def get(self, request: Request) -> Response:
        asset_class = request.query_params.get("asset_class", "crypto")

        from analysis.services.signal_service import SignalService

        health = SignalService.get_pipeline_health(asset_class)
        return Response(health)


class EntryCheckView(InternalAPIView):
    """Entry gate for Freqtrade — internal calls only."""

    @extend_schema(
        request=EntryCheckRequestSerializer,
        responses=EntryCheckResponseSerializer,
        tags=["Signals"],
    )
    def post(self, request: Request, symbol: str) -> Response:
        from analysis.services.signal_service import SignalService

        real_symbol = symbol.replace("-", "/")
        strategy = request.data.get("strategy", "CryptoInvestorV1")
        asset_class = request.data.get("asset_class", "crypto")

        try:
            rec = SignalService.get_entry_recommendation(
                real_symbol, strategy, asset_class,
            )
            return Response(rec)
        except Exception as e:
            # Fail-open: approve on error (consistent with risk gate pattern)
            return Response({
                "approved": True,
                "score": 0.0,
                "position_modifier": 1.0,
                "reasoning": [f"Signal service error (fail-open): {e}"],
                "signal_label": "unknown",
                "hard_disabled": False,
            })


class StrategyStatusView(InternalAPIView):
    """Which strategies should be active given current regime conditions.

    Internal — called by Freqtrade bot_loop_start() and frontend.
    """

    @extend_schema(
        responses=StrategyStatusSerializer(many=True),
        tags=["Signals"],
        parameters=[
            OpenApiParameter(
                "asset_class", str, description="Asset class",
                enum=["crypto", "equity", "forex"],
            ),
        ],
    )
    def get(self, request: Request) -> Response:
        asset_class = request.query_params.get("asset_class", "crypto")

        # Prefer orchestrator persisted state (updated every 15min by scheduled task)
        try:
            from trading.services.strategy_orchestrator import StrategyOrchestrator

            orchestrator = StrategyOrchestrator.get_instance()
            states = orchestrator.get_all_states()
            results = [
                {
                    "strategy_name": s.strategy,
                    "asset_class": s.asset_class,
                    "regime": s.regime,
                    "alignment_score": s.alignment,
                    "recommended_action": s.action,
                }
                for s in states
                if s.asset_class == asset_class
            ]
            if results:
                return Response(results)
        except Exception:
            pass

        # Fallback: compute fresh (before first orchestrator run)
        from core.platform_bridge import ensure_platform_imports

        strategy_map = {
            "crypto": ["CryptoInvestorV1", "BollingerMeanReversion", "VolatilityBreakout"],
            "equity": ["EquityMomentum", "EquityMeanReversion"],
            "forex": ["ForexTrend", "ForexRange"],
        }

        strategies = strategy_map.get(asset_class, strategy_map["crypto"])
        results = []

        try:
            ensure_platform_imports()
            from common.data_pipeline.pipeline import load_ohlcv
            from common.regime.regime_detector import RegimeDetector
            from common.signals.constants import ALIGNMENT_TABLES

            detector = RegimeDetector()
            rep_symbols = {
                "crypto": "BTC/USDT",
                "equity": "SPY",
                "forex": "EUR/USD",
            }
            sym = rep_symbols.get(asset_class, "BTC/USDT")
            exchange_id = "yfinance" if asset_class in ("equity", "forex") else "kraken"
            df = load_ohlcv(sym, "1h", exchange_id)
            if df is None or df.empty:
                raise ValueError(f"No data for {sym}")
            state = detector.detect(df)

            table = ALIGNMENT_TABLES.get(asset_class, ALIGNMENT_TABLES["crypto"])
            regime_row = table.get(state.regime, {})

            for strat in strategies:
                alignment = regime_row.get(strat, 50)
                from trading.services.strategy_orchestrator import StrategyOrchestrator

                if alignment <= StrategyOrchestrator.PAUSE_THRESHOLD:
                    action = "pause"
                elif alignment <= StrategyOrchestrator.REDUCE_THRESHOLD:
                    action = "reduce_size"
                else:
                    action = "active"

                results.append({
                    "strategy_name": strat,
                    "asset_class": asset_class,
                    "regime": state.regime.value,
                    "alignment_score": alignment,
                    "recommended_action": action,
                })
        except Exception:
            for strat in strategies:
                results.append({
                    "strategy_name": strat,
                    "asset_class": asset_class,
                    "regime": "unknown",
                    "alignment_score": 50,
                    "recommended_action": "active",
                })

        return Response(results)


# ── ML Prediction tracking views ─────────────────────────────


class MLPredictionListView(APIView):
    """Recent ML predictions for a symbol — audit trail."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=MLPredictionSerializer(many=True),
        tags=["ML"],
        parameters=[
            OpenApiParameter("limit", int, description="Max results (default 50, max 200)"),
        ],
    )
    def get(self, request: Request, symbol: str) -> Response:
        real_symbol = symbol.replace("-", "/")
        limit = _safe_int(request.query_params.get("limit"), 50, max_val=200)
        preds = MLPrediction.objects.filter(symbol=real_symbol).order_by("-predicted_at")[:limit]
        return Response(MLPredictionSerializer(preds, many=True).data)


class MLModelPerformanceView(APIView):
    """Model accuracy metrics and retraining recommendations."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MLModelPerformanceSerializer, tags=["ML"])
    def get(self, request: Request, model_id: str) -> Response:
        try:
            perf = MLModelPerformance.objects.get(model_id=model_id)
        except MLModelPerformance.DoesNotExist:
            return Response(
                {"error": "Model performance data not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(MLModelPerformanceSerializer(perf).data)


# ── Signal Attribution & Feedback views ──────────────────────────────


class SignalAttributionListView(APIView):
    """List signal attributions with optional filters."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=SignalAttributionSerializer(many=True),
        tags=["Signals"],
        parameters=[
            OpenApiParameter("asset_class", str, description="Filter by asset class"),
            OpenApiParameter("strategy", str, description="Filter by strategy"),
            OpenApiParameter("outcome", str, description="Filter by outcome (win/loss/open)"),
            OpenApiParameter("limit", int, description="Max results (default 50, max 200)"),
        ],
    )
    def get(self, request: Request) -> Response:
        qs = SignalAttribution.objects.all()
        asset_class = request.query_params.get("asset_class")
        strategy = request.query_params.get("strategy")
        outcome = request.query_params.get("outcome")
        limit = _safe_int(request.query_params.get("limit"), 50, max_val=200)

        if asset_class:
            qs = qs.filter(asset_class=asset_class)
        if strategy:
            qs = qs.filter(strategy=strategy)
        if outcome and outcome in ("win", "loss", "open"):
            qs = qs.filter(outcome=outcome)

        return Response(SignalAttributionSerializer(qs[:limit], many=True).data)


class SignalAttributionDetailView(APIView):
    """Get a single signal attribution by order_id."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=SignalAttributionSerializer, tags=["Signals"])
    def get(self, request: Request, order_id: str) -> Response:
        attr = SignalAttribution.objects.filter(order_id=order_id).first()
        if attr is None:
            return Response(
                {"error": "Attribution not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(SignalAttributionSerializer(attr).data)


class SignalRecordView(InternalAPIView):
    """Record signal attribution at trade entry — internal calls only."""

    @extend_schema(
        request=RecordAttributionRequestSerializer,
        responses=SignalAttributionSerializer,
        tags=["Signals"],
    )
    def post(self, request: Request) -> Response:
        ser = RecordAttributionRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from analysis.services.signal_feedback import SignalFeedbackService

        result = SignalFeedbackService.record_attribution(
            order_id=ser.validated_data["order_id"],
            symbol=ser.validated_data["symbol"],
            asset_class=ser.validated_data["asset_class"],
            strategy=ser.validated_data["strategy"],
            signal_data=ser.validated_data["signal_data"],
        )
        return Response(result, status=status.HTTP_201_CREATED)


class SignalFeedbackView(APIView):
    """Backfill outcome for a signal attribution."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=BackfillOutcomeRequestSerializer,
        responses=SignalAttributionSerializer,
        tags=["Signals"],
    )
    def post(self, request: Request) -> Response:
        ser = BackfillOutcomeRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        attr = SignalAttribution.objects.filter(
            order_id=ser.validated_data["order_id"],
        ).first()
        if attr is None:
            return Response(
                {"error": "Attribution not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from django.utils import timezone as tz

        attr.outcome = ser.validated_data["outcome"]
        attr.pnl = ser.validated_data.get("pnl")
        attr.resolved_at = tz.now()
        attr.save(update_fields=["outcome", "pnl", "resolved_at"])
        return Response(SignalAttributionSerializer(attr).data)


class SignalAccuracyView(APIView):
    """Signal source accuracy statistics."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=SourceAccuracyResponseSerializer,
        tags=["Signals"],
        parameters=[
            OpenApiParameter("asset_class", str, description="Filter by asset class"),
            OpenApiParameter("strategy", str, description="Filter by strategy"),
            OpenApiParameter("window_days", int, description="Lookback days (default 30)"),
        ],
    )
    def get(self, request: Request) -> Response:
        from analysis.services.signal_feedback import SignalFeedbackService

        asset_class = request.query_params.get("asset_class")
        strategy = request.query_params.get("strategy")
        window_days = _safe_int(request.query_params.get("window_days"), 30, max_val=365)

        result = SignalFeedbackService.get_source_accuracy(
            asset_class=asset_class,
            strategy=strategy,
            window_days=window_days,
        )
        return Response(result)


class SignalWeightsView(APIView):
    """Current and recommended signal weights based on performance."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=WeightRecommendationResponseSerializer,
        tags=["Signals"],
        parameters=[
            OpenApiParameter("asset_class", str, description="Filter by asset class"),
            OpenApiParameter("strategy", str, description="Filter by strategy"),
            OpenApiParameter("window_days", int, description="Lookback days (default 30)"),
        ],
    )
    def get(self, request: Request) -> Response:
        from analysis.services.signal_feedback import SignalFeedbackService

        asset_class = request.query_params.get("asset_class")
        strategy = request.query_params.get("strategy")
        window_days = _safe_int(request.query_params.get("window_days"), 30, max_val=365)

        result = SignalFeedbackService.get_weight_recommendations(
            asset_class=asset_class,
            strategy=strategy,
            window_days=window_days,
        )
        return Response(result)
