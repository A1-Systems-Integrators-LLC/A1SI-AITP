"""Core views — health, platform status, platform config, metrics, CSRF failure."""

import logging

from django.http import HttpResponse, JsonResponse
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


def csrf_failure(request, reason="") -> JsonResponse:
    """Return JSON 403 instead of Django's default HTML CSRF error page."""
    return JsonResponse(
        {"error": "CSRF verification failed.", "detail": reason},
        status=403,
    )


class HealthView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Core"])
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class PlatformStatusView(APIView):
    @extend_schema(tags=["Core"])
    def get(self, request: Request) -> Response:
        from analysis.models import BackgroundJob
        from core.platform_bridge import get_processed_dir

        # Framework status
        frameworks = _get_framework_status()

        # Data summary
        processed = get_processed_dir()
        data_files = len(list(processed.glob("*.parquet")))

        # Active jobs
        active_jobs = BackgroundJob.objects.filter(status__in=["pending", "running"]).count()

        return Response(
            {
                "frameworks": frameworks,
                "data_files": data_files,
                "active_jobs": active_jobs,
            }
        )


class PlatformConfigView(APIView):
    @extend_schema(tags=["Core"])
    def get(self, request: Request) -> Response:
        from core.platform_bridge import get_platform_config_path

        config_path = get_platform_config_path()
        if not config_path.exists():
            return Response({"error": "platform_config.yaml not found"})
        try:
            import yaml

            with open(config_path) as f:
                return Response(yaml.safe_load(f) or {})
        except ImportError:
            return Response({"raw": config_path.read_text()[:5000]})


class NotificationPreferencesView(APIView):
    @extend_schema(tags=["Notifications"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        from core.models import NotificationPreferences
        from core.serializers import NotificationPreferencesSerializer

        prefs, _ = NotificationPreferences.objects.get_or_create(portfolio_id=portfolio_id)
        return Response(NotificationPreferencesSerializer(prefs).data)

    @extend_schema(tags=["Notifications"])
    def put(self, request: Request, portfolio_id: int) -> Response:
        from core.models import NotificationPreferences
        from core.serializers import NotificationPreferencesSerializer

        prefs, _ = NotificationPreferences.objects.get_or_create(portfolio_id=portfolio_id)
        ser = NotificationPreferencesSerializer(prefs, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class MetricsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Core"], exclude=True)
    def get(self, request: Request) -> HttpResponse:
        from core.services.metrics import metrics
        from portfolio.models import Portfolio
        from risk.models import RiskState
        from trading.models import Order, OrderStatus, TradingMode

        # Snapshot current state into gauges
        try:
            live_orders = Order.objects.filter(
                mode=TradingMode.LIVE,
                status__in=[OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIAL_FILL],
            ).count()
            paper_orders = Order.objects.filter(
                mode=TradingMode.PAPER,
                status__in=[OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIAL_FILL],
            ).count()
            metrics.gauge("active_orders", live_orders, {"mode": "live"})
            metrics.gauge("active_orders", paper_orders, {"mode": "paper"})
        except Exception:
            logger.warning("Failed to snapshot order metrics", exc_info=True)

        try:
            primary = Portfolio.objects.order_by("id").values_list("id", flat=True).first()
            if primary:
                state = RiskState.objects.filter(portfolio_id=primary).first()
                if state:
                    metrics.gauge("portfolio_equity", state.total_equity)
                    peak = state.peak_equity if state.peak_equity > 0 else 1
                    metrics.gauge("portfolio_drawdown", 1.0 - (state.total_equity / peak))
                    metrics.gauge("risk_halt_active", 1.0 if state.is_halted else 0.0)
        except Exception:
            logger.warning("Failed to snapshot risk metrics", exc_info=True)

        return HttpResponse(metrics.collect(), content_type="text/plain; charset=utf-8")


# ── Scheduler views ──────────────────────────────────────────


class SchedulerStatusView(APIView):
    @extend_schema(tags=["Scheduler"])
    def get(self, request: Request) -> Response:
        from core.services.scheduler import get_scheduler

        return Response(get_scheduler().get_status())


class ScheduledTaskListView(APIView):
    @extend_schema(tags=["Scheduler"])
    def get(self, request: Request) -> Response:
        from core.models import ScheduledTask
        from core.serializers import ScheduledTaskSerializer

        tasks = ScheduledTask.objects.all()
        return Response(ScheduledTaskSerializer(tasks, many=True).data)


class ScheduledTaskDetailView(APIView):
    @extend_schema(tags=["Scheduler"])
    def get(self, request: Request, task_id: str) -> Response:
        from core.models import ScheduledTask
        from core.serializers import ScheduledTaskSerializer

        try:
            task = ScheduledTask.objects.get(id=task_id)
        except ScheduledTask.DoesNotExist:
            return Response({"error": "Task not found"}, status=404)
        return Response(ScheduledTaskSerializer(task).data)


class ScheduledTaskPauseView(APIView):
    @extend_schema(tags=["Scheduler"])
    def post(self, request: Request, task_id: str) -> Response:
        from core.services.scheduler import get_scheduler

        if get_scheduler().pause_task(task_id):
            return Response({"message": f"Task {task_id} paused"})
        return Response({"error": "Task not found"}, status=404)


class ScheduledTaskResumeView(APIView):
    @extend_schema(tags=["Scheduler"])
    def post(self, request: Request, task_id: str) -> Response:
        from core.services.scheduler import get_scheduler

        if get_scheduler().resume_task(task_id):
            return Response({"message": f"Task {task_id} resumed"})
        return Response({"error": "Task not found"}, status=404)


class ScheduledTaskTriggerView(APIView):
    @extend_schema(tags=["Scheduler"])
    def post(self, request: Request, task_id: str) -> Response:
        from core.services.scheduler import get_scheduler

        job_id = get_scheduler().trigger_task(task_id)
        if job_id:
            return Response({
                "job_id": job_id,
                "task_id": task_id,
                "message": f"Task {task_id} triggered",
            })
        return Response({"error": "Task not found or no executor"}, status=404)


def _get_framework_status() -> list[dict]:
    from core.platform_bridge import PROJECT_ROOT

    def _try_import(module_name: str) -> str | None:
        """Try to import a module and return its version, or None on failure."""
        try:
            mod = __import__(module_name)
            return getattr(mod, "__version__", "installed")
        except Exception:
            return None

    def _check(name: str, module: str, fallback_path: str | None = None) -> dict:
        """Check framework availability via import, falling back to file presence."""
        ver = _try_import(module)
        if ver:
            return {"name": name, "installed": True, "version": ver}
        # Fallback: check if framework files are deployed on disk
        if fallback_path and (PROJECT_ROOT / fallback_path).exists():
            return {"name": name, "installed": True, "version": "configured"}
        return {"name": name, "installed": False, "version": None}

    return [
        _check("VectorBT", "vectorbt", "research/scripts/vbt_screener.py"),
        _check("Freqtrade", "freqtrade", "freqtrade/user_data/strategies"),
        _check("NautilusTrader", "nautilus_trader", "nautilus/nautilus_runner.py"),
        _check("HFT Backtest", "hftbacktest", "hftbacktest"),
        _check("CCXT", "ccxt"),
        _check("Pandas", "pandas"),
        _check("TA-Lib", "talib"),
    ]
