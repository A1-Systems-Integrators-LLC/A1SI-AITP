"""Core views — health, platform status, platform config, metrics, CSRF failure."""

import contextlib
import logging

from django.conf import settings as django_settings
from django.http import HttpResponse, JsonResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import (
    AuditLogListResponseSerializer,
    DashboardKPISerializer,
    DetailedHealthResponseSerializer,
    NotificationPreferencesSerializer,
    PlatformStatusSerializer,
    ScheduledTaskSerializer,
    SchedulerStatusSerializer,
    TaskActionResponseSerializer,
    TaskTriggerResponseSerializer,
)

logger = logging.getLogger(__name__)


def csrf_failure(request, reason="") -> JsonResponse:
    """Return JSON 403 instead of Django's default HTML CSRF error page."""
    return JsonResponse(
        {"error": "CSRF verification failed.", "detail": reason},
        status=403,
    )


class MetricsTokenOrSessionAuth(BasePermission):
    """Allow access via Bearer token (for Prometheus) or session auth (browser)."""

    def has_permission(self, request, view):
        token = getattr(django_settings, "METRICS_AUTH_TOKEN", "")
        if token:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            if auth_header == f"Bearer {token}":
                return True
        return bool(request.user and request.user.is_authenticated)


class AuditLogListView(APIView):
    @extend_schema(
        responses=AuditLogListResponseSerializer,
        tags=["Core"],
        parameters=[
            OpenApiParameter("user", str, description="Filter by username"),
            OpenApiParameter(
                "action", str, description="Filter by action (case-insensitive contains)"
            ),
            OpenApiParameter("status_code", int, description="Filter by HTTP status code"),
            OpenApiParameter(
                "created_after", str, description="Filter entries after this ISO datetime"
            ),
            OpenApiParameter(
                "created_before", str, description="Filter entries before this ISO datetime"
            ),
            OpenApiParameter("limit", int, description="Max results (default 50, max 200)"),
            OpenApiParameter("offset", int, description="Pagination offset (default 0)"),
        ],
    )
    def get(self, request: Request) -> Response:
        from core.models import AuditLog
        from core.serializers import AuditLogSerializer
        from core.utils import safe_int

        qs = AuditLog.objects.all()

        # Filters
        user = request.query_params.get("user")
        if user:
            qs = qs.filter(user=user)

        action = request.query_params.get("action")
        if action:
            qs = qs.filter(action__icontains=action)

        status_code = request.query_params.get("status_code")
        if status_code:
            with contextlib.suppress(ValueError, TypeError):
                qs = qs.filter(status_code=int(status_code))

        created_after = request.query_params.get("created_after")
        if created_after:
            qs = qs.filter(created_at__gte=created_after)

        created_before = request.query_params.get("created_before")
        if created_before:
            qs = qs.filter(created_at__lte=created_before)

        total = qs.count()

        # Pagination
        limit = safe_int(request.query_params.get("limit"), 50, max_val=200)
        offset = safe_int(request.query_params.get("offset"), 0)
        entries = qs[offset : offset + limit]

        return Response(
            {
                "results": AuditLogSerializer(entries, many=True).data,
                "total": total,
            }
        )


class HealthView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: DetailedHealthResponseSerializer},
        tags=["Core"],
    )
    def get(self, request: Request) -> Response:
        if request.query_params.get("detailed") != "true":
            return Response({"status": "ok"})

        checks = {}

        # Database check
        try:
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["database"] = {"status": "ok"}
        except Exception as e:
            checks["database"] = {"status": "error", "detail": str(e)}

        # Disk check
        try:
            import os
            import shutil

            from core.platform_bridge import get_processed_dir

            data_dir = get_processed_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(str(data_dir))
            writable = os.access(str(data_dir), os.W_OK)
            checks["disk"] = {
                "status": "ok" if writable else "error",
                "total_gb": round(usage.total / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "used_pct": round(usage.used / usage.total * 100, 1),
                "writable": writable,
            }
        except Exception as e:
            checks["disk"] = {"status": "error", "detail": str(e)}

        # Memory check
        try:
            import platform
            import resource

            usage_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # On Linux, ru_maxrss is in KB; on macOS it's in bytes
            if platform.system() == "Darwin":
                usage_mb = usage_kb / (1024 * 1024)
            else:
                usage_mb = usage_kb / 1024
            checks["memory"] = {
                "status": "ok",
                "rss_mb": round(usage_mb, 1),
            }
        except Exception as e:
            checks["memory"] = {"status": "error", "detail": str(e)}

        # Scheduler check
        try:
            from core.services.scheduler import get_scheduler

            sched = get_scheduler()
            checks["scheduler"] = {
                "running": sched.running,
            }
        except Exception as e:
            checks["scheduler"] = {"status": "error", "detail": str(e)}

        # Circuit breaker check
        try:
            from market.services.circuit_breaker import get_all_breakers

            breaker_states = {b["exchange_id"]: b["state"] for b in get_all_breakers()}
            checks["circuit_breakers"] = breaker_states
        except Exception as e:
            checks["circuit_breakers"] = {"status": "error", "detail": str(e)}

        # Channel layer check
        try:
            from channels.layers import get_channel_layer

            layer = get_channel_layer()
            checks["channel_layer"] = {
                "status": "ok" if layer is not None else "warning",
                "backend": type(layer).__name__ if layer else "none",
            }
        except Exception as e:
            checks["channel_layer"] = {"status": "error", "detail": str(e)}

        # Job queue staleness check
        try:
            from django.utils import timezone

            from analysis.models import BackgroundJob

            pending_jobs = BackgroundJob.objects.filter(status="pending").order_by("created_at")
            oldest = pending_jobs.first()
            if oldest:
                age_minutes = (timezone.now() - oldest.created_at).total_seconds() / 60
                checks["job_queue"] = {
                    "status": "warning" if age_minutes > 30 else "ok",
                    "oldest_pending_minutes": round(age_minutes, 1),
                    "pending_count": pending_jobs.count(),
                }
            else:
                checks["job_queue"] = {"status": "ok", "pending_count": 0}
        except Exception as e:
            checks["job_queue"] = {"status": "error", "detail": str(e)}

        # WAL check
        try:
            import os

            db_path = str(django_settings.DATABASES["default"]["NAME"])
            wal_path = db_path + "-wal"
            wal_size_mb = os.path.getsize(wal_path) / (1024**2) if os.path.exists(wal_path) else 0
            checks["wal"] = {
                "status": "ok" if wal_size_mb < 100 else "warning",
                "size_mb": round(wal_size_mb, 2),
            }
        except Exception as e:
            checks["wal"] = {"status": "error", "detail": str(e)}

        overall = "ok" if all(
            c.get("status", "ok") == "ok" for c in checks.values() if isinstance(c, dict)
        ) else "degraded"
        return Response({"status": overall, "checks": checks})


class DashboardKPIView(APIView):
    @extend_schema(
        responses=DashboardKPISerializer,
        tags=["Core"],
        parameters=[
            OpenApiParameter(
                "asset_class",
                str,
                description="Filter KPIs by asset class",
                enum=["crypto", "equity", "forex"],
            ),
        ],
    )
    def get(self, request: Request) -> Response:
        from core.services.dashboard import DashboardService

        asset_class = request.query_params.get("asset_class")
        return Response(DashboardService.get_kpis(asset_class))


class PlatformStatusView(APIView):
    @extend_schema(responses=PlatformStatusSerializer, tags=["Core"])
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
    @extend_schema(responses=NotificationPreferencesSerializer, tags=["Notifications"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        from core.models import NotificationPreferences

        prefs, _ = NotificationPreferences.objects.get_or_create(portfolio_id=portfolio_id)
        return Response(NotificationPreferencesSerializer(prefs).data)

    @extend_schema(
        request=NotificationPreferencesSerializer,
        responses=NotificationPreferencesSerializer,
        tags=["Notifications"],
    )
    def put(self, request: Request, portfolio_id: int) -> Response:
        from core.models import NotificationPreferences

        prefs, _ = NotificationPreferences.objects.get_or_create(portfolio_id=portfolio_id)
        ser = NotificationPreferencesSerializer(prefs, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class MetricsView(APIView):
    permission_classes = [MetricsTokenOrSessionAuth]

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

        # Job queue depth
        try:
            from analysis.models import BackgroundJob

            pending = BackgroundJob.objects.filter(status="pending").count()
            running = BackgroundJob.objects.filter(status="running").count()
            metrics.gauge("job_queue_pending", pending)
            metrics.gauge("job_queue_running", running)
        except Exception:
            logger.warning("Failed to snapshot job queue metrics", exc_info=True)

        # Circuit breaker state
        try:
            from market.services.circuit_breaker import get_all_breakers

            for breaker_info in get_all_breakers():
                state_val = {"open": 1, "half_open": 0.5, "closed": 0}.get(
                    breaker_info["state"], 0
                )
                metrics.gauge(
                    "circuit_breaker_state",
                    state_val,
                    {"exchange": breaker_info["exchange_id"]},
                )
        except Exception:
            logger.warning("Failed to snapshot circuit breaker metrics", exc_info=True)

        # Scheduler health
        try:
            from core.services.scheduler import get_scheduler

            sched = get_scheduler()
            metrics.gauge("scheduler_running", 1 if sched.running else 0)
        except Exception:
            logger.warning("Failed to snapshot scheduler metrics", exc_info=True)

        return HttpResponse(metrics.collect(), content_type="text/plain; charset=utf-8")


# ── Scheduler views ──────────────────────────────────────────


class SchedulerStatusView(APIView):
    @extend_schema(responses=SchedulerStatusSerializer, tags=["Scheduler"])
    def get(self, request: Request) -> Response:
        from core.services.scheduler import get_scheduler

        return Response(get_scheduler().get_status())


class ScheduledTaskListView(APIView):
    @extend_schema(responses=ScheduledTaskSerializer(many=True), tags=["Scheduler"])
    def get(self, request: Request) -> Response:
        from core.models import ScheduledTask

        tasks = ScheduledTask.objects.all()
        return Response(ScheduledTaskSerializer(tasks, many=True).data)


class ScheduledTaskDetailView(APIView):
    @extend_schema(responses=ScheduledTaskSerializer, tags=["Scheduler"])
    def get(self, request: Request, task_id: str) -> Response:
        from core.models import ScheduledTask

        try:
            task = ScheduledTask.objects.get(id=task_id)
        except ScheduledTask.DoesNotExist:
            return Response({"error": "Task not found"}, status=404)
        return Response(ScheduledTaskSerializer(task).data)


class ScheduledTaskPauseView(APIView):
    @extend_schema(responses=TaskActionResponseSerializer, tags=["Scheduler"])
    def post(self, request: Request, task_id: str) -> Response:
        from core.services.scheduler import get_scheduler

        if get_scheduler().pause_task(task_id):
            return Response({"message": f"Task {task_id} paused"})
        return Response({"error": "Task not found"}, status=404)


class ScheduledTaskResumeView(APIView):
    @extend_schema(responses=TaskActionResponseSerializer, tags=["Scheduler"])
    def post(self, request: Request, task_id: str) -> Response:
        from core.services.scheduler import get_scheduler

        if get_scheduler().resume_task(task_id):
            return Response({"message": f"Task {task_id} resumed"})
        return Response({"error": "Task not found"}, status=404)


class ScheduledTaskTriggerView(APIView):
    @extend_schema(responses=TaskTriggerResponseSerializer, tags=["Scheduler"])
    def post(self, request: Request, task_id: str) -> Response:
        from core.services.scheduler import get_scheduler

        job_id = get_scheduler().trigger_task(task_id)
        if job_id:
            return Response(
                {
                    "job_id": job_id,
                    "task_id": task_id,
                    "message": f"Task {task_id} triggered",
                }
            )
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
