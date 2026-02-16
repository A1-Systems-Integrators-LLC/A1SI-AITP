"""Analysis views — jobs, backtest, screening, data pipeline."""


from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from analysis.models import BackgroundJob, BacktestResult, ScreenResult
from analysis.serializers import (
    BacktestRequestSerializer,
    BacktestResultSerializer,
    JobSerializer,
    ScreenRequestSerializer,
    ScreenResultSerializer,
)


class JobListView(APIView):
    def get(self, request: Request) -> Response:
        job_type = request.query_params.get("job_type")
        limit = int(request.query_params.get("limit", 50))
        qs = BackgroundJob.objects.all()
        if job_type:
            qs = qs.filter(job_type=job_type)
        jobs = qs[:limit]
        return Response(JobSerializer(jobs, many=True).data)


class JobDetailView(APIView):
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
    def get(self, request: Request) -> Response:
        limit = int(request.query_params.get("limit", 20))
        results = BacktestResult.objects.select_related("job").all()[:limit]
        return Response(BacktestResultSerializer(results, many=True).data)


class BacktestResultDetailView(APIView):
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
    def get(self, request: Request) -> Response:
        from analysis.services.backtest import BacktestService

        return Response(BacktestService.list_strategies())


class BacktestCompareView(APIView):
    def get(self, request: Request) -> Response:
        ids_param = request.query_params.get("ids", "")
        id_list = [int(x) for x in ids_param.split(",") if x.strip()]
        results = BacktestResult.objects.select_related("job").filter(id__in=id_list)
        return Response(BacktestResultSerializer(results, many=True).data)


class ScreeningRunView(APIView):
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
    def get(self, request: Request) -> Response:
        limit = int(request.query_params.get("limit", 20))
        results = ScreenResult.objects.select_related("job").all()[:limit]
        return Response(ScreenResultSerializer(results, many=True).data)


class ScreeningResultDetailView(APIView):
    def get(self, request: Request, result_id: int) -> Response:
        try:
            result = ScreenResult.objects.select_related("job").get(id=result_id)
        except ScreenResult.DoesNotExist:
            return Response({"error": "Screen result not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(ScreenResultSerializer(result).data)


class ScreeningStrategyListView(APIView):
    def get(self, request: Request) -> Response:
        from analysis.services.screening import STRATEGY_TYPES

        return Response(STRATEGY_TYPES)


class DataListView(APIView):
    def get(self, request: Request) -> Response:
        from analysis.services.data_pipeline import DataPipelineService

        svc = DataPipelineService()
        return Response(svc.list_available_data())


class DataDetailView(APIView):
    def get(self, request: Request, exchange: str, symbol: str, timeframe: str) -> Response:
        from analysis.services.data_pipeline import DataPipelineService

        real_symbol = symbol.replace("_", "/")
        svc = DataPipelineService()
        info = svc.get_data_info(real_symbol, timeframe, exchange)
        if not info:
            return Response({"error": "Data file not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(info)


class DataDownloadView(APIView):
    def post(self, request: Request) -> Response:
        from analysis.serializers import DataDownloadRequestSerializer
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
    def post(self, request: Request) -> Response:
        from analysis.serializers import DataGenerateSampleRequestSerializer
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
