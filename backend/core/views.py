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

        return Response({
            "frameworks": frameworks,
            "data_files": data_files,
            "active_jobs": active_jobs,
        })


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

    @extend_schema(tags=["Core"], exclude=True)
    def get(self, request: Request) -> HttpResponse:
        from core.services.metrics import metrics
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
            pass

        try:
            state = RiskState.objects.filter(portfolio_id=1).first()
            if state:
                metrics.gauge("portfolio_equity", state.total_equity)
                peak = state.peak_equity if state.peak_equity > 0 else 1
                metrics.gauge("portfolio_drawdown", 1.0 - (state.total_equity / peak))
                metrics.gauge("risk_halt_active", 1.0 if state.is_halted else 0.0)
        except Exception:
            pass

        return HttpResponse(metrics.collect(), content_type="text/plain; charset=utf-8")


def _get_framework_status() -> list[dict]:
    frameworks = []

    try:
        import vectorbt as vbt
        frameworks.append({"name": "VectorBT", "installed": True, "version": vbt.__version__})
    except ImportError:
        frameworks.append({"name": "VectorBT", "installed": False, "version": None})

    try:
        import freqtrade
        ver = getattr(freqtrade, "__version__", "installed")
        frameworks.append({"name": "Freqtrade", "installed": True, "version": ver})
    except ImportError:
        frameworks.append({"name": "Freqtrade", "installed": False, "version": None})

    try:
        import nautilus_trader
        ver = getattr(nautilus_trader, "__version__", "installed")
        frameworks.append({"name": "NautilusTrader", "installed": True, "version": ver})
    except ImportError:
        frameworks.append({"name": "NautilusTrader", "installed": False, "version": None})

    try:
        import ccxt
        frameworks.append({"name": "CCXT", "installed": True, "version": ccxt.__version__})
    except ImportError:
        frameworks.append({"name": "CCXT", "installed": False, "version": None})

    try:
        import pandas as pd
        frameworks.append({"name": "Pandas", "installed": True, "version": pd.__version__})
    except ImportError:
        frameworks.append({"name": "Pandas", "installed": False, "version": None})

    return frameworks
